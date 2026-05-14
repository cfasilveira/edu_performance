"""
tests/infrastructure/test_docker_compose.py
============================================
Testes de validação da infraestrutura Docker.
Agente 1 — DevOps & Infra.

Valida sem iniciar containers:
- docker-compose.yml estrutura, portas e limites
- Variáveis de ambiente obrigatórias
- Volumes e rede isolada
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def compose_data() -> dict:
    """Carrega docker-compose.yml como dicionário."""
    compose_file = ROOT / "docker-compose.yml"
    assert compose_file.exists(), "docker-compose.yml não encontrado"
    with open(compose_file, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def services(compose_data: dict) -> dict:
    return compose_data.get("services", {})


# ---------------------------------------------------------------------------
# Testes de estrutura
# ---------------------------------------------------------------------------

class TestComposeStructure:
    def test_required_services_exist(self, services):
        assert "edu-mvp" in services, "Serviço 'edu-mvp' ausente"
        assert "edu-db" in services, "Serviço 'edu-db' ausente"

    def test_network_defined(self, compose_data):
        networks = compose_data.get("networks", {})
        assert "edu-net" in networks, "Rede 'edu-net' não definida"
        assert networks["edu-net"]["driver"] == "bridge"

    def test_volume_defined(self, compose_data):
        volumes = compose_data.get("volumes", {})
        assert "edu-db-data" in volumes, "Volume 'edu-db-data' não definido"

    def test_compose_valid_syntax(self):
        """Valida o compose via docker (se disponível)."""
        try:
            result = subprocess.run(
                ["docker", "compose", "config", "--quiet"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"docker compose config falhou:\n{result.stderr}"
        except FileNotFoundError:
            pytest.skip("Docker não disponível neste ambiente de teste")


# ---------------------------------------------------------------------------
# Testes de portas
# ---------------------------------------------------------------------------

class TestPorts:
    def test_app_port(self, services):
        ports = services["edu-mvp"].get("ports", [])
        assert any("8501" in str(p) for p in ports), (
            "Porta 8501 não exposta para edu-mvp"
        )

    def test_db_port_5433(self, services):
        """5433 no host (não 5432) para evitar conflito com postgres local."""
        ports = services["edu-db"].get("ports", [])
        assert any("5433" in str(p) for p in ports), (
            "Porta 5433 não exposta para edu-db (usar 5433, não 5432)"
        )

    def test_db_does_not_expose_5432_directly(self, services):
        """5432 não deve ser exposta diretamente no host."""
        ports = services["edu-db"].get("ports", [])
        for port in ports:
            host_port = str(port).split(":")[0]
            assert host_port != "5432", "edu-db não deve expor 5432 no host"


# ---------------------------------------------------------------------------
# Testes de resource limits
# ---------------------------------------------------------------------------

class TestResourceLimits:
    def test_app_cpu_limit(self, services):
        limits = services["edu-mvp"].get("deploy", {}).get("resources", {}).get("limits", {})
        cpus = float(limits.get("cpus", 0))
        assert cpus <= 4.0, f"edu-mvp: CPU limit deve ser ≤ 4 cores, encontrado: {cpus}"
        assert cpus > 0, "edu-mvp: CPU limit não definido"

    def test_app_memory_limit(self, services):
        limits = services["edu-mvp"].get("deploy", {}).get("resources", {}).get("limits", {})
        mem = limits.get("memory", "")
        assert "4G" in str(mem) or "4096M" in str(mem), (
            f"edu-mvp: Memória deve ser 4G, encontrado: {mem}"
        )

    def test_db_cpu_limit(self, services):
        limits = services["edu-db"].get("deploy", {}).get("resources", {}).get("limits", {})
        cpus = float(limits.get("cpus", 0))
        assert cpus <= 2.0, f"edu-db: CPU limit deve ser ≤ 2 cores, encontrado: {cpus}"

    def test_db_memory_limit(self, services):
        limits = services["edu-db"].get("deploy", {}).get("resources", {}).get("limits", {})
        mem = limits.get("memory", "")
        assert "1G" in str(mem) or "1024M" in str(mem), (
            f"edu-db: Memória deve ser 1G, encontrado: {mem}"
        )


# ---------------------------------------------------------------------------
# Testes de healthcheck
# ---------------------------------------------------------------------------

class TestHealthchecks:
    def test_app_has_healthcheck(self, services):
        hc = services["edu-mvp"].get("healthcheck", {})
        assert hc, "edu-mvp não tem healthcheck"
        assert "8501" in str(hc.get("test", "")), "Healthcheck deve verificar porta 8501"

    def test_db_has_healthcheck(self, services):
        hc = services["edu-db"].get("healthcheck", {})
        assert hc, "edu-db não tem healthcheck"
        assert "pg_isready" in str(hc.get("test", "")), "Healthcheck do DB deve usar pg_isready"

    def test_app_depends_on_db_healthy(self, services):
        depends = services["edu-mvp"].get("depends_on", {})
        assert "edu-db" in depends, "edu-mvp deve depender de edu-db"
        condition = depends["edu-db"].get("condition", "")
        assert condition == "service_healthy", (
            "edu-mvp deve aguardar edu-db estar healthy, não apenas started"
        )


# ---------------------------------------------------------------------------
# Testes de rede e Ollama
# ---------------------------------------------------------------------------

class TestNetworkAndOllama:
    def test_app_in_edu_net(self, services):
        networks = services["edu-mvp"].get("networks", [])
        assert "edu-net" in networks, "edu-mvp não está na rede edu-net"

    def test_db_in_edu_net(self, services):
        networks = services["edu-db"].get("networks", [])
        assert "edu-net" in networks, "edu-db não está na rede edu-net"

    def test_host_internal_extra_host(self, services):
        extra_hosts = services["edu-mvp"].get("extra_hosts", [])
        assert any("host.docker.internal" in str(h) for h in extra_hosts), (
            "edu-mvp precisa de extra_hosts com host.docker.internal para acessar Ollama"
        )


# ---------------------------------------------------------------------------
# Testes de segurança
# ---------------------------------------------------------------------------

class TestSecurity:
    def test_env_file_not_committed(self):
        env_file = ROOT / ".env"
        # .env pode existir localmente, mas não deve estar no git
        result = subprocess.run(
            ["git", "log", "--all", "--name-only", "--format=", "--", ".env"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        assert ".env" not in result.stdout, (
            "CRÍTICO: .env foi commitado no histórico git!"
        )

    def test_env_example_exists(self):
        assert (ROOT / ".env.example").exists(), ".env.example deve existir"

    def test_dockerignore_exists(self):
        assert (ROOT / ".dockerignore").exists(), ".dockerignore deve existir"

    def test_init_sql_idempotent(self):
        """Verifica que init.sql usa IF NOT EXISTS (idempotente)."""
        sql_file = ROOT / "config" / "init.sql"
        assert sql_file.exists(), "config/init.sql não encontrado"
        content = sql_file.read_text(encoding="utf-8")
        assert "IF NOT EXISTS" in content, "init.sql deve ser idempotente (CREATE ... IF NOT EXISTS)"
        assert "PII" in content or "LGPD" in content, "init.sql deve ter comentários de conformidade LGPD"
