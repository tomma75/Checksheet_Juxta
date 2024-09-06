from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from datetime import datetime, timedelta
import ipaddress

# 개인 키 생성
key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
)

# 인증서 생성
subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COUNTRY_NAME, u"KR"),
    x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"State"),
    x509.NameAttribute(NameOID.LOCALITY_NAME, u"City"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Organization"),
    x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
])
cert = x509.CertificateBuilder().subject_name(
    subject
).issuer_name(
    issuer
).public_key(
    key.public_key()
).serial_number(
    x509.random_serial_number()
).not_valid_before(
    datetime.utcnow()
).not_valid_after(
    datetime.utcnow() + timedelta(days=365)
).add_extension(
    x509.SubjectAlternativeName([
        x509.DNSName(u"localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
    ]),
    critical=False,
).sign(key, hashes.SHA256())

# 개인 키를 파일로 저장
with open("server.key", "wb") as f:
    f.write(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))

# 인증서를 파일로 저장
with open("server.crt", "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))

print("server.key와 server.crt 파일이 생성되었습니다.")