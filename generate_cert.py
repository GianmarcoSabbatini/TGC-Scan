"""
Generate self-signed SSL certificate for local HTTPS development.
This allows camera access from mobile devices on the local network.
"""
from OpenSSL import crypto
import os

def generate_self_signed_cert(cert_file='cert.pem', key_file='key.pem'):
    """Generate a self-signed certificate for HTTPS"""
    
    # Check if certificates already exist
    if os.path.exists(cert_file) and os.path.exists(key_file):
        print(f"Certificates already exist: {cert_file}, {key_file}")
        return cert_file, key_file
    
    # Create a key pair
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 2048)
    
    # Create a self-signed cert
    cert = crypto.X509()
    cert.get_subject().C = "IT"
    cert.get_subject().ST = "Local"
    cert.get_subject().L = "Local"
    cert.get_subject().O = "TGC-Scan"
    cert.get_subject().OU = "Development"
    cert.get_subject().CN = "192.168.1.9"  # Your local IP
    
    # Add Subject Alternative Names for both localhost and IP
    san = b"DNS:localhost,DNS:127.0.0.1,IP:127.0.0.1,IP:192.168.1.9"
    cert.add_extensions([
        crypto.X509Extension(b"subjectAltName", False, san)
    ])
    
    cert.set_serial_number(1000)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(365 * 24 * 60 * 60)  # Valid for 1 year
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)
    cert.sign(k, 'sha256')
    
    # Save certificate
    with open(cert_file, "wb") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    
    # Save private key
    with open(key_file, "wb") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))
    
    print(f"Generated self-signed certificate: {cert_file}")
    print(f"Generated private key: {key_file}")
    print(f"Certificate valid for: localhost, 127.0.0.1, 192.168.1.9")
    
    return cert_file, key_file


if __name__ == '__main__':
    generate_self_signed_cert()
