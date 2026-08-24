import ipaddress

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from orchestrator.gateway.certificates import generate_local_tls


def test_cross_platform_generator_reuses_ca_and_reissues_leaf(tmp_path):
    generate_local_tls(tmp_path, ["192.168.4.20", "tutor.local"])
    ca_first = x509.load_pem_x509_certificate((tmp_path / "rootCA.pem").read_bytes())
    leaf_first = x509.load_pem_x509_certificate((tmp_path / "fullchain.pem").read_bytes())

    generate_local_tls(tmp_path, ["192.168.4.21"])
    ca_second = x509.load_pem_x509_certificate((tmp_path / "rootCA.pem").read_bytes())
    leaf_second = x509.load_pem_x509_certificate((tmp_path / "fullchain.pem").read_bytes())

    assert ca_first.fingerprint(hashes.SHA256()) == ca_second.fingerprint(hashes.SHA256())
    assert leaf_first.serial_number != leaf_second.serial_number
    sans = leaf_second.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert ipaddress.ip_address("192.168.4.21") in sans.get_values_for_type(x509.IPAddress)
    assert "localhost" in sans.get_values_for_type(x509.DNSName)

    ca_public = ca_second.public_key()
    ca_public.verify(
        leaf_second.signature,
        leaf_second.tbs_certificate_bytes,
        padding.PKCS1v15(),
        leaf_second.signature_hash_algorithm,
    )
