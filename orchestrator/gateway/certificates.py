"""Cross-platform offline CA and LAN server-certificate generation."""

from __future__ import annotations

import ipaddress
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


class CertificateError(RuntimeError):
    pass


def _write_private(path: Path, key) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass


def generate_local_tls(cert_dir: Path, hosts: list[str], *, force: bool = False) -> None:
    """Create/reuse Muta's local CA and issue a leaf for ``hosts`` without shell tools."""
    cert_dir.mkdir(parents=True, exist_ok=True)
    ca_pem = cert_dir / "rootCA.pem"
    ca_key_path = cert_dir / "rootCA.key"
    leaf_pem = cert_dir / "fullchain.pem"
    leaf_key_path = cert_dir / "privkey.pem"

    have_ca = ca_pem.is_file()
    have_key = ca_key_path.is_file()
    if have_ca != have_key and not force:
        raise CertificateError(
            "incomplete local CA; both rootCA.pem and rootCA.key are required"
        )

    now = datetime.now(timezone.utc)
    if force or not (have_ca and have_key):
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
        ca_name = x509.Name(
            [
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Muta Local CA"),
                x509.NameAttribute(NameOID.COMMON_NAME, "Muta Local Root CA"),
            ]
        )
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=False,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), False)
            .sign(ca_key, hashes.SHA256())
        )
        _write_private(ca_key_path, ca_key)
        ca_pem.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    else:
        try:
            ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
            ca_cert = x509.load_pem_x509_certificate(ca_pem.read_bytes())
        except (OSError, ValueError, TypeError) as exc:
            raise CertificateError("the existing local CA cannot be loaded") from exc

    dns_names = ["localhost"]
    ip_names = [ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1")]
    for raw in hosts:
        value = raw.strip().strip("[]")
        if not value:
            continue
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            if value not in dns_names:
                dns_names.append(value)
        else:
            if address not in ip_names:
                ip_names.append(address)

    common_name = next((item.strip().strip("[]") for item in hosts if item.strip()), "localhost")
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_name = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Muta Local"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )
    sans = [x509.DNSName(name) for name in dns_names]
    sans.extend(x509.IPAddress(address) for address in ip_names)
    leaf_cert = (
        x509.CertificateBuilder()
        .subject_name(leaf_name)
        .issuer_name(ca_cert.subject)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=825))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
        .add_extension(x509.SubjectAlternativeName(sans), False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False)
        .sign(ca_key, hashes.SHA256())
    )

    try:
        ca_cert.public_key().verify(
            leaf_cert.signature,
            leaf_cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            leaf_cert.signature_hash_algorithm,
        )
    except (InvalidSignature, TypeError, ValueError) as exc:
        raise CertificateError("issued certificate did not verify against the local CA") from exc

    _write_private(leaf_key_path, leaf_key)
    leaf_pem.write_bytes(leaf_cert.public_bytes(serialization.Encoding.PEM))
    for public_file in (ca_pem, leaf_pem):
        try:
            os.chmod(public_file, 0o644)
        except OSError:
            pass
