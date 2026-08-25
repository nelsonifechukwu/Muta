use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Component, Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use tauri::{Emitter, Manager, RunEvent};

#[cfg(unix)]
use std::os::unix::process::CommandExt;
#[cfg(windows)]
use std::os::windows::io::AsRawHandle;

const STARTUP_TIMEOUT: Duration = Duration::from_secs(240);
const READY_POLL_INTERVAL: Duration = Duration::from_millis(350);

#[derive(Debug, Deserialize)]
struct ProductManifest {
    model_pack_id: String,
}

#[derive(Debug, Deserialize)]
struct ModelPackManifest {
    pack_id: String,
    files: Vec<FileEntry>,
}

#[derive(Debug, Deserialize)]
struct FileEntry {
    path: String,
    size_bytes: u64,
    sha256: String,
}

#[derive(Debug, Deserialize)]
struct ActivePointer {
    pack_id: String,
    path: String,
}

struct BackendProcess {
    child: Child,
    stopped: bool,
    #[cfg(windows)]
    job: isize,
    #[cfg(unix)]
    process_group: i32,
}

impl BackendProcess {
    fn shutdown(&mut self) {
        if self.stopped {
            return;
        }
        self.stopped = true;
        #[cfg(windows)]
        unsafe {
            use windows_sys::Win32::Foundation::CloseHandle;
            if self.job != 0 {
                // KILL_ON_JOB_CLOSE terminates the frozen gateway and every llama/tool child.
                CloseHandle(self.job as _);
                self.job = 0;
            }
        }
        #[cfg(unix)]
        unsafe {
            libc::kill(-self.process_group, libc::SIGTERM);
        }

        let deadline = Instant::now() + Duration::from_secs(8);
        while Instant::now() < deadline {
            if self.child.try_wait().ok().flatten().is_some() {
                return;
            }
            thread::sleep(Duration::from_millis(100));
        }
        #[cfg(unix)]
        unsafe {
            libc::kill(-self.process_group, libc::SIGKILL);
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        self.shutdown();
    }
}

struct ProcessState(Mutex<Option<BackendProcess>>);

fn available_port() -> Result<u16, String> {
    let listener = TcpListener::bind(("127.0.0.1", 0)).map_err(|error| error.to_string())?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| error.to_string())
}

fn read_json<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T, String> {
    let body = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    serde_json::from_str(&body).map_err(|error| format!("{}: {error}", path.display()))
}

fn safe_relative(value: &str) -> Result<PathBuf, String> {
    let path = Path::new(value);
    if path.as_os_str().is_empty()
        || path.is_absolute()
        || path.components().any(|component| {
            matches!(
                component,
                Component::ParentDir | Component::RootDir | Component::Prefix(_)
            )
        })
    {
        return Err(format!("unsafe model-pack path: {value}"));
    }
    Ok(path.to_path_buf())
}

fn hash_file(path: &Path) -> Result<String, String> {
    let mut stream = File::open(path).map_err(|error| format!("{}: {error}", path.display()))?;
    let mut digest = Sha256::new();
    let mut buffer = vec![0_u8; 8 * 1024 * 1024];
    loop {
        let read = stream
            .read(&mut buffer)
            .map_err(|error| error.to_string())?;
        if read == 0 {
            break;
        }
        digest.update(&buffer[..read]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn decode_tauri_signature(value: &str) -> Result<String, String> {
    if value.starts_with("untrusted comment:") {
        return Ok(value.to_string());
    }
    use base64::Engine;
    let decoded = base64::engine::general_purpose::STANDARD
        .decode(value.trim())
        .map_err(|error| format!("invalid detached-signature encoding: {error}"))?;
    String::from_utf8(decoded).map_err(|error| format!("detached signature is not UTF-8: {error}"))
}

fn decode_tauri_public_key(value: &str) -> Result<String, String> {
    if value.starts_with("untrusted comment:") {
        return Ok(value.to_string());
    }
    use base64::Engine;
    let decoded = base64::engine::general_purpose::STANDARD
        .decode(value.trim())
        .map_err(|error| format!("invalid public-key encoding: {error}"))?;
    let document =
        String::from_utf8(decoded).map_err(|error| format!("public key is not UTF-8: {error}"))?;
    if !document.starts_with("untrusted comment:") {
        return Err("decoded public key is not a minisign document".to_string());
    }
    Ok(document)
}

fn verify_model_pack(root: &Path, required_id: &str) -> Result<ModelPackManifest, String> {
    if let Some(encoded_key) = option_env!("MUTA_MODEL_PACK_PUBLIC_KEY") {
        use minisign_verify::{PublicKey, Signature};
        let manifest_path = root.join("model-pack.json");
        let signature_path = root.join("model-pack.json.sig");
        let public_key_document = decode_tauri_public_key(encoded_key)?;
        let public_key = PublicKey::decode(&public_key_document)
            .map_err(|error| format!("invalid embedded model-pack public key: {error}"))?;
        // Tauri's signer writes the complete four-line minisign document inside one outer
        // base64 layer (the format its updater API consumes). Decode that layer before using
        // the independent minisign verifier for model packs.
        let encoded_signature = fs::read_to_string(&signature_path).map_err(|error| {
            format!("model-pack signature {}: {error}", signature_path.display())
        })?;
        let signature_document = decode_tauri_signature(&encoded_signature)?;
        let signature = Signature::decode(&signature_document)
            .map_err(|error| format!("model-pack signature is malformed: {error}"))?;
        let content = fs::read(&manifest_path)
            .map_err(|error| format!("{}: {error}", manifest_path.display()))?;
        public_key
            .verify(&content, &signature, false)
            .map_err(|error| format!("model-pack signature is not trusted: {error}"))?;
    }
    let manifest: ModelPackManifest = read_json(&root.join("model-pack.json"))?;
    if manifest.pack_id != required_id {
        return Err(format!(
            "model pack {} does not match required pack {required_id}",
            manifest.pack_id
        ));
    }
    for entry in &manifest.files {
        let relative = safe_relative(&entry.path)?;
        let path = root.join(relative);
        let metadata =
            fs::symlink_metadata(&path).map_err(|error| format!("{}: {error}", path.display()))?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(format!(
                "model-pack member is not a regular file: {}",
                path.display()
            ));
        }
        if metadata.len() != entry.size_bytes {
            return Err(format!("model-pack byte size mismatch: {}", entry.path));
        }
        if hash_file(&path)? != entry.sha256 {
            return Err(format!("model-pack SHA-256 mismatch: {}", entry.path));
        }
    }
    Ok(manifest)
}

fn copy_model_pack(
    source: &Path,
    destination: &Path,
    manifest: &ModelPackManifest,
) -> Result<(), String> {
    fs::create_dir_all(destination).map_err(|error| error.to_string())?;
    for entry in &manifest.files {
        let relative = safe_relative(&entry.path)?;
        let from = source.join(&relative);
        let to = destination.join(&relative);
        if let Some(parent) = to.parent() {
            fs::create_dir_all(parent).map_err(|error| error.to_string())?;
        }
        fs::copy(&from, &to)
            .map_err(|error| format!("copying {} to {}: {error}", from.display(), to.display()))?;
    }
    fs::copy(
        source.join("model-pack.json"),
        destination.join("model-pack.json"),
    )
    .map_err(|error| error.to_string())?;
    let signature = source.join("model-pack.json.sig");
    if signature.is_file() {
        fs::copy(signature, destination.join("model-pack.json.sig"))
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

fn valid_custom_gguf(path: &Path) -> bool {
    let Ok(metadata) = fs::symlink_metadata(path) else {
        return false;
    };
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return false;
    }
    let Ok(mut stream) = File::open(path) else {
        return false;
    };
    let mut header = [0_u8; 8];
    if stream.read_exact(&mut header).is_err() || &header[..4] != b"GGUF" {
        return false;
    }
    matches!(u32::from_le_bytes(header[4..8].try_into().unwrap()), 2 | 3)
}

fn custom_files_below(root: &Path, current: &Path, found: &mut Vec<(PathBuf, PathBuf)>) {
    let Ok(entries) = fs::read_dir(current) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let Ok(kind) = entry.file_type() else {
            continue;
        };
        if kind.is_symlink() {
            continue;
        }
        if kind.is_dir() {
            custom_files_below(root, &path, found);
        } else if path
            .extension()
            .and_then(|value| value.to_str())
            .is_some_and(|value| value.eq_ignore_ascii_case("gguf"))
            && valid_custom_gguf(&path)
        {
            if let Ok(relative) = path.strip_prefix(root) {
                found.push((path.clone(), relative.to_path_buf()));
            }
        }
    }
}

fn sync_custom_models(source: &Path, destination: &Path) -> Result<(), String> {
    let mut files = Vec::new();
    // A literal GGUF in model-pack is accepted for convenience and normalised into the
    // dedicated custom directory. Nested files belong below models/custom.
    if let Ok(entries) = fs::read_dir(source) {
        for entry in entries.flatten() {
            let path = entry.path();
            if valid_custom_gguf(&path) {
                files.push((path, PathBuf::from(entry.file_name())));
            }
        }
    }
    let custom = source.join("models/custom");
    if custom.is_dir() {
        custom_files_below(&custom, &custom, &mut files);
    }
    for (from, relative) in files {
        let relative = safe_relative(&relative.to_string_lossy())?;
        let to = destination.join("models/custom").join(relative);
        if from.canonicalize().ok() == to.canonicalize().ok() && to.is_file() {
            continue;
        }
        if let Some(parent) = to.parent() {
            fs::create_dir_all(parent).map_err(|error| error.to_string())?;
        }
        let temporary = to.with_extension(format!("gguf.incoming-{}", std::process::id()));
        fs::copy(&from, &temporary)
            .map_err(|error| format!("copying custom model {}: {error}", from.display()))?;
        if !valid_custom_gguf(&temporary) {
            let _ = fs::remove_file(&temporary);
            return Err(format!(
                "custom model changed while copying: {}",
                from.display()
            ));
        }
        replace_file(&temporary, &to)?;
    }
    Ok(())
}

#[cfg(windows)]
fn replace_file(source: &Path, destination: &Path) -> Result<(), String> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{
        MoveFileExW, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH,
    };
    let mut from: Vec<u16> = source.as_os_str().encode_wide().chain(Some(0)).collect();
    let mut to: Vec<u16> = destination
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect();
    let result = unsafe {
        MoveFileExW(
            from.as_mut_ptr(),
            to.as_mut_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if result == 0 {
        Err(std::io::Error::last_os_error().to_string())
    } else {
        Ok(())
    }
}

#[cfg(not(windows))]
fn replace_file(source: &Path, destination: &Path) -> Result<(), String> {
    fs::rename(source, destination).map_err(|error| error.to_string())
}

fn install_model_pack(
    source: &Path,
    data_root: &Path,
    required_id: &str,
) -> Result<PathBuf, String> {
    let manifest = verify_model_pack(source, required_id)?;
    let store = data_root.join("model-packs");
    let packs = store.join("packs");
    fs::create_dir_all(&packs).map_err(|error| error.to_string())?;
    // A human-readable pack id is not a content version: a promoted model may change while the
    // product still calls the pack `muta-models-2026.08`. Store each verified manifest in its own
    // immutable directory so upgrades never reuse stale bytes or overwrite a mmap-open GGUF.
    let manifest_hash = hash_file(&source.join("model-pack.json"))?;
    let destination = packs.join(format!("{}-{manifest_hash}", manifest.pack_id));
    if !destination.is_dir() {
        let incoming = packs.join(format!(
            ".incoming-{}-{}-{manifest_hash}",
            std::process::id(),
            manifest.pack_id
        ));
        if incoming.exists() {
            fs::remove_dir_all(&incoming).map_err(|error| error.to_string())?;
        }
        copy_model_pack(source, &incoming, &manifest)?;
        // Preserve valid user-added GGUFs from the previously active version before switching
        // the pointer. Base files remain governed exclusively by the new signed manifest.
        let pointer_path = store.join("active.json");
        if let Ok(previous) = read_json::<ActivePointer>(&pointer_path) {
            if previous.pack_id == required_id {
                if let Ok(relative) = safe_relative(&previous.path) {
                    sync_custom_models(&store.join(relative), &incoming)?;
                }
            }
        }
        sync_custom_models(source, &incoming)?;
        verify_model_pack(&incoming, required_id)?;
        fs::rename(&incoming, &destination).map_err(|error| error.to_string())?;
    } else {
        if let Err(verification_error) = verify_model_pack(&destination, required_id) {
            // The content-addressed destination should be immutable. If it was interrupted or
            // corrupted, rebuild it beside the old directory and swap only after verification.
            let incoming = packs.join(format!(
                ".repair-{}-{}-{manifest_hash}",
                std::process::id(),
                manifest.pack_id
            ));
            let backup = packs.join(format!(
                ".replaced-{}-{}-{manifest_hash}",
                std::process::id(),
                manifest.pack_id
            ));
            let _ = fs::remove_dir_all(&incoming);
            let _ = fs::remove_dir_all(&backup);
            copy_model_pack(source, &incoming, &manifest)?;
            sync_custom_models(&destination, &incoming)?;
            sync_custom_models(source, &incoming)?;
            verify_model_pack(&incoming, required_id)?;
            fs::rename(&destination, &backup).map_err(|error| {
                format!("replacing corrupt model pack after {verification_error}: {error}")
            })?;
            if let Err(error) = fs::rename(&incoming, &destination) {
                let _ = fs::rename(&backup, &destination);
                return Err(format!("installing repaired model pack: {error}"));
            }
            fs::remove_dir_all(&backup).map_err(|error| error.to_string())?;
        }
        sync_custom_models(source, &destination)?;
    }
    let pointer = ActivePointer {
        pack_id: manifest.pack_id,
        path: destination
            .strip_prefix(&store)
            .map_err(|error| error.to_string())?
            .to_string_lossy()
            .replace('\\', "/"),
    };
    let temporary = store.join(format!("active-{}.tmp", std::process::id()));
    fs::write(
        &temporary,
        serde_json::to_vec_pretty(&serde_json::json!({
            "pack_id": pointer.pack_id,
            "path": pointer.path,
        }))
        .map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())?;
    replace_file(&temporary, &store.join("active.json"))?;
    Ok(destination)
}

fn candidate_model_roots(data_root: &Path, required_id: &str) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(explicit) = std::env::var_os("MUTA_MODEL_ROOT") {
        candidates.push(PathBuf::from(explicit));
    }
    let mut anchors = Vec::new();
    if let Some(appimage) = std::env::var_os("APPIMAGE") {
        anchors.push(PathBuf::from(appimage));
    }
    if let Ok(executable) = std::env::current_exe() {
        anchors.push(executable);
    }
    for anchor in anchors {
        for ancestor in anchor.ancestors().take(7) {
            candidates.push(ancestor.join("model-pack"));
            candidates.push(ancestor.join("model-packs").join(required_id));
        }
    }
    // Prefer first-install media over the active installed pointer. This lets a user add a
    // GGUF beside Muta and simply reopen the app: the launcher re-verifies the immutable base
    // pack, imports new custom models, then atomically updates the installed copy.
    let pointer_path = data_root.join("model-packs/active.json");
    if let Ok(pointer) = read_json::<ActivePointer>(&pointer_path) {
        if pointer.pack_id == required_id {
            if let Ok(relative) = safe_relative(&pointer.path) {
                candidates.push(data_root.join("model-packs").join(relative));
            }
        }
    }
    candidates
}

fn resolve_model_root(data_root: &Path, required_id: &str) -> Result<PathBuf, String> {
    let mut errors = Vec::new();
    for candidate in candidate_model_roots(data_root, required_id) {
        if !candidate.join("model-pack.json").is_file() {
            continue;
        }
        match verify_model_pack(&candidate, required_id) {
            Ok(_) => return Ok(candidate),
            Err(error) => errors.push(format!("{}: {error}", candidate.display())),
        }
    }
    Err(format!(
        "The verified model pack {required_id} is not installed. Keep the release's model-pack folder beside the portable app, or close Muta and run it with --install-model-pack <folder>.{}",
        if errors.is_empty() {
            String::new()
        } else {
            format!("\nRejected candidates:\n{}", errors.join("\n"))
        }
    ))
}

fn parse_ready_response(response: &[u8]) -> bool {
    let Some(split) = response.windows(4).position(|window| window == b"\r\n\r\n") else {
        return false;
    };
    let headers = String::from_utf8_lossy(&response[..split]);
    if !headers.starts_with("HTTP/1.1 200") && !headers.starts_with("HTTP/1.0 200") {
        return false;
    }
    serde_json::from_slice::<serde_json::Value>(&response[split + 4..])
        .ok()
        .and_then(|body| body.get("ready").and_then(|value| value.as_bool()))
        == Some(true)
}

fn backend_ready(port: u16) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(250)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    if write!(
        stream,
        "GET /v1/ready HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
    )
    .is_err()
    {
        return false;
    }
    let mut response = Vec::new();
    stream.read_to_end(&mut response).is_ok() && parse_ready_response(&response)
}

#[cfg(windows)]
fn assign_kill_job(child: &Child) -> Result<isize, String> {
    use std::mem::{size_of, zeroed};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    unsafe {
        let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if job.is_null() {
            return Err(std::io::Error::last_os_error().to_string());
        }
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = zeroed();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &info as *const _ as _,
            size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        ) == 0
            || AssignProcessToJobObject(job, child.as_raw_handle() as _) == 0
        {
            windows_sys::Win32::Foundation::CloseHandle(job);
            return Err(std::io::Error::last_os_error().to_string());
        }
        Ok(job as isize)
    }
}

fn spawn_backend(
    gateway: &Path,
    resources: &Path,
    model_root: &Path,
    data_root: &Path,
    cache_root: &Path,
    gateway_port: u16,
    engine_port: u16,
) -> Result<BackendProcess, String> {
    let logs = data_root.join("logs");
    fs::create_dir_all(&logs).map_err(|error| error.to_string())?;
    let stdout = OpenOptions::new()
        .create(true)
        .append(true)
        .open(logs.join("desktop-backend.log"))
        .map_err(|error| error.to_string())?;
    let stderr = stdout.try_clone().map_err(|error| error.to_string())?;
    let mut command = Command::new(gateway);
    command
        .arg("--serve")
        .arg("--resource-root")
        .arg(resources)
        .arg("--model-root")
        .arg(model_root)
        .arg("--data-root")
        .arg(data_root)
        .arg("--cache-root")
        .arg(cache_root)
        .arg("--llama-server")
        .arg(resources.join("bin").join(if cfg!(windows) {
            "llama-server.exe"
        } else {
            "llama-server"
        }))
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(gateway_port.to_string())
        .arg("--engine-port")
        .arg(engine_port.to_string())
        .arg("--parent-pid")
        .arg(std::process::id().to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr));
    #[cfg(unix)]
    command.process_group(0);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        use windows_sys::Win32::System::Threading::CREATE_NO_WINDOW;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    let child = command
        .spawn()
        .map_err(|error| format!("starting backend: {error}"))?;
    #[cfg(windows)]
    let (child, job) = match assign_kill_job(&child) {
        Ok(job) => (child, job),
        Err(error) => {
            let mut child = child;
            let _ = child.kill();
            let _ = child.wait();
            return Err(format!("assigning backend process job: {error}"));
        }
    };
    #[cfg(unix)]
    let process_group = child.id() as i32;
    Ok(BackendProcess {
        child,
        stopped: false,
        #[cfg(windows)]
        job,
        #[cfg(unix)]
        process_group,
    })
}

fn launch(app: tauri::AppHandle) -> Result<(), String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|error| error.to_string())?;
    let resources = resource_dir.join("resources");
    let gateway = resource_dir.join("gateway").join(if cfg!(windows) {
        "muta-gateway.exe"
    } else {
        "muta-gateway"
    });
    let data_root = app
        .path()
        .app_local_data_dir()
        .map_err(|error| error.to_string())?;
    let cache_root = app
        .path()
        .app_cache_dir()
        .map_err(|error| error.to_string())?;
    fs::create_dir_all(&data_root).map_err(|error| error.to_string())?;
    fs::create_dir_all(&cache_root).map_err(|error| error.to_string())?;
    let product: ProductManifest = read_json(&resources.join("desktop-product.json"))?;

    app.emit("backend-status", "Verifying the offline model pack…")
        .map_err(|error| error.to_string())?;
    let install_argument = std::env::args_os()
        .collect::<Vec<_>>()
        .windows(2)
        .find(|pair| pair[0] == "--install-model-pack")
        .map(|pair| PathBuf::from(&pair[1]));
    let model_root = if let Some(source) = install_argument {
        install_model_pack(&source, &data_root, &product.model_pack_id)?
    } else {
        let resolved = resolve_model_root(&data_root, &product.model_pack_id)?;
        let installed_store = data_root.join("model-packs").join("packs");
        // A model pack beside first-install media is only a source. Persist it in the
        // versioned user store so the app/flash drive can move independently afterwards.
        if std::env::var_os("MUTA_MODEL_ROOT").is_none() && !resolved.starts_with(&installed_store)
        {
            install_model_pack(&resolved, &data_root, &product.model_pack_id)?
        } else {
            resolved
        }
    };

    for attempt in 1..=5 {
        let gateway_port = available_port()?;
        let mut engine_port = available_port()?;
        while engine_port == gateway_port {
            engine_port = available_port()?;
        }
        app.emit(
            "backend-status",
            format!("Loading the local model… (attempt {attempt}/5)"),
        )
        .map_err(|error| error.to_string())?;
        let mut backend = spawn_backend(
            &gateway,
            &resources,
            &model_root,
            &data_root,
            &cache_root,
            gateway_port,
            engine_port,
        )?;
        let deadline = Instant::now() + STARTUP_TIMEOUT;
        while Instant::now() < deadline {
            if let Some(status) = backend
                .child
                .try_wait()
                .map_err(|error| error.to_string())?
            {
                if attempt == 5 {
                    return Err(format!(
                        "The local backend exited with {status}. See {}.",
                        data_root.join("logs/desktop-backend.log").display()
                    ));
                }
                break;
            }
            if backend_ready(gateway_port) {
                let state = app.state::<ProcessState>();
                *state.0.lock().map_err(|_| "backend state lock poisoned")? = Some(backend);
                let url = tauri::Url::parse(&format!("http://127.0.0.1:{gateway_port}/chat/"))
                    .map_err(|error| error.to_string())?;
                app.get_webview_window("main")
                    .ok_or("main window is missing")?
                    .navigate(url)
                    .map_err(|error| error.to_string())?;
                return Ok(());
            }
            thread::sleep(READY_POLL_INTERVAL);
        }
        backend.shutdown();
    }
    Err("Muta could not reserve local ports after five attempts".to_string())
}

fn shutdown(app: &tauri::AppHandle) {
    let state = app.state::<ProcessState>();
    if let Ok(mut guard) = state.0.lock() {
        if let Some(mut process) = guard.take() {
            process.shutdown();
        }
    };
}

fn main() {
    let mut builder = tauri::Builder::default()
        // Must be the first plugin so duplicate launches cannot start duplicate model trees.
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }));
    // Unsigned developer packages contain no updater config. Release CI opts in at compile
    // time and supplies the public key/HTTPS endpoint through its generated config overlay.
    if option_env!("MUTA_UPDATER_ENABLED") == Some("1") {
        builder = builder.plugin(tauri_plugin_updater::Builder::new().build());
    }
    let app = builder
        .manage(ProcessState(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            thread::spawn(move || {
                if let Err(error) = launch(handle.clone()) {
                    let _ = handle.emit("backend-error", error);
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error building Muta desktop application");

    app.run(|handle, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            shutdown(handle);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn readiness_requires_json_true_not_only_http_200() {
        assert!(!parse_ready_response(
            b"HTTP/1.1 200 OK\r\ncontent-length: 15\r\n\r\n{\"ready\":false}"
        ));
        assert!(parse_ready_response(
            b"HTTP/1.1 200 OK\r\ncontent-length: 14\r\n\r\n{\"ready\":true}"
        ));
    }

    #[test]
    fn model_pack_paths_cannot_escape() {
        assert!(safe_relative("models/core/model.gguf").is_ok());
        assert!(safe_relative("../model.gguf").is_err());
        assert!(safe_relative("/tmp/model.gguf").is_err());
    }

    #[test]
    fn custom_gguf_requires_magic_and_supported_version() {
        let root = std::env::temp_dir().join(format!("muta-custom-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let valid = root.join("valid.gguf");
        fs::write(&valid, [b'G', b'G', b'U', b'F', 3, 0, 0, 0]).unwrap();
        let invalid = root.join("invalid.gguf");
        fs::write(&invalid, b"not a model").unwrap();
        assert!(valid_custom_gguf(&valid));
        assert!(!valid_custom_gguf(&invalid));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn first_install_media_precedes_the_installed_pointer() {
        let data_root =
            std::env::temp_dir().join(format!("muta-candidate-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&data_root);
        let pointer_root = data_root.join("model-packs/packs/current");
        fs::create_dir_all(data_root.join("model-packs")).unwrap();
        fs::create_dir_all(&pointer_root).unwrap();
        fs::write(
            data_root.join("model-packs/active.json"),
            br#"{"pack_id":"test-pack","path":"packs/current"}"#,
        )
        .unwrap();

        let candidates = candidate_model_roots(&data_root, "test-pack");
        assert_eq!(candidates.last(), Some(&pointer_root));
        fs::remove_dir_all(data_root).unwrap();
    }

    fn write_test_pack(root: &Path, payload: &[u8]) {
        let model = root.join("models/core/model.gguf");
        fs::create_dir_all(model.parent().unwrap()).unwrap();
        fs::write(&model, payload).unwrap();
        let sha256 = hash_file(&model).unwrap();
        fs::write(
            root.join("model-pack.json"),
            serde_json::to_vec_pretty(&serde_json::json!({
                "schema": 1,
                "pack_id": "test-pack",
                "active_model_id": "test-model",
                "files": [{
                    "path": "models/core/model.gguf",
                    "size_bytes": payload.len(),
                    "sha256": sha256,
                }],
            }))
            .unwrap(),
        )
        .unwrap();
    }

    #[test]
    fn model_pack_upgrade_replaces_stale_content_and_preserves_custom_models() {
        let root =
            std::env::temp_dir().join(format!("muta-pack-upgrade-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        let data_root = root.join("data");
        let first_source = root.join("first");
        let second_source = root.join("second");
        write_test_pack(&first_source, b"old model bytes");
        write_test_pack(&second_source, b"new promoted model bytes");

        let first = install_model_pack(&first_source, &data_root, "test-pack").unwrap();
        let custom = first.join("models/custom/teacher.gguf");
        fs::create_dir_all(custom.parent().unwrap()).unwrap();
        fs::write(&custom, [b'G', b'G', b'U', b'F', 3, 0, 0, 0]).unwrap();

        let second = install_model_pack(&second_source, &data_root, "test-pack").unwrap();

        assert_ne!(first, second);
        assert_eq!(
            fs::read(second.join("models/core/model.gguf")).unwrap(),
            b"new promoted model bytes"
        );
        assert!(second.join("models/custom/teacher.gguf").is_file());
        let pointer: ActivePointer = read_json(&data_root.join("model-packs/active.json")).unwrap();
        assert_eq!(data_root.join("model-packs").join(pointer.path), second);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn tauri_signature_outer_base64_is_unwrapped() {
        use base64::Engine;
        let document = "untrusted comment: signature\nbody\ntrusted comment: timestamp\nglobal\n";
        let encoded = base64::engine::general_purpose::STANDARD.encode(document);
        assert_eq!(decode_tauri_signature(&encoded).unwrap(), document);
        assert_eq!(decode_tauri_signature(document).unwrap(), document);
    }

    #[test]
    fn tauri_public_key_outer_base64_is_unwrapped() {
        use base64::Engine;
        let document = "untrusted comment: minisign public key\nRWQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n";
        let encoded = base64::engine::general_purpose::STANDARD.encode(document);
        assert_eq!(decode_tauri_public_key(&encoded).unwrap(), document);
        assert_eq!(decode_tauri_public_key(document).unwrap(), document);
    }
}
