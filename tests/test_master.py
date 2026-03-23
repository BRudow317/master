import os
from dataclasses import dataclass, field
def main():
    
    @dataclass
    class OracleClient:
        oracle_user: str | None = field(default_factory=lambda: os.environ.get('ORACLE_USER'))
        oracle_pass: str | None = field(default_factory=lambda: os.environ.get('ORACLE_PASS'))
        oracle_host: str | None = field(default_factory=lambda: os.environ.get('ORACLE_HOST'))
        oracle_port: int | None = field(default_factory=lambda: int(p) if (p := os.environ.get('ORACLE_PORT', '1521')).isdigit() else 0)
        oracle_service: str | None = field(default_factory=lambda: os.environ.get('ORACLE_SID'))

        def __post_init__(self):
            print("--OracleClient initialized---\n\n")
    client = OracleClient()
    print(f"Oracle User: {client.oracle_user}")
    print(f"Oracle Pass: {client.oracle_pass}")
    print(f"Oracle Host: {client.oracle_host}")
    print(f"Oracle Port: {client.oracle_port}")
    print(f"Oracle Service: {client.oracle_service}")
if __name__ == "__main__":
    main()