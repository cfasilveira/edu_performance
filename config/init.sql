-- =============================================================================
-- config/init.sql — EduAnalytics MVP
-- Inicialização idempotente do banco PostgreSQL.
-- LGPD by Design: nenhuma coluna armazena PII diretamente.
-- Todas as referências a alunos usam student_hash (SHA-256[:12]).
-- =============================================================================

-- Extensão para UUIDs
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- TABELA: grade_records
-- Notas pseudonimizadas por aluno/disciplina/período.
-- NÃO armazene nome, CPF, e-mail ou telefone nesta tabela.
-- =============================================================================
CREATE TABLE IF NOT EXISTS grade_records (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    student_hash  CHAR(12)    NOT NULL,                   -- SHA-256[:12] do ID original
    class_id      VARCHAR(50) NOT NULL,
    subject       VARCHAR(50) NOT NULL,
    grade         NUMERIC(5,1) NOT NULL CHECK (grade >= 0 AND grade <= 100),
    period        VARCHAR(10) NOT NULL,                   -- ex: 2024-T1
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id     VARCHAR(50) NOT NULL DEFAULT 'school_mvp'
);

CREATE INDEX IF NOT EXISTS idx_grade_student ON grade_records (student_hash);
CREATE INDEX IF NOT EXISTS idx_grade_subject ON grade_records (subject);
CREATE INDEX IF NOT EXISTS idx_grade_period  ON grade_records (period);
CREATE INDEX IF NOT EXISTS idx_grade_tenant  ON grade_records (tenant_id);

-- =============================================================================
-- TABELA: grouping_results
-- Grupos cross-turma gerados pelo algoritmo de agrupamento.
-- =============================================================================
CREATE TABLE IF NOT EXISTS grouping_results (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id             VARCHAR(50) NOT NULL UNIQUE,
    student_hashes       TEXT[]      NOT NULL,            -- array de hashes (sem PII)
    shared_weaknesses    TEXT[]      NOT NULL,
    similarity_score     NUMERIC(4,3) CHECK (similarity_score >= 0 AND similarity_score <= 1),
    recommended_intervention TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id            VARCHAR(50) NOT NULL DEFAULT 'school_mvp'
);

CREATE INDEX IF NOT EXISTS idx_group_tenant ON grouping_results (tenant_id);

-- =============================================================================
-- TABELA: ai_recommendations
-- Recomendações pedagógicas geradas pela IA (requerem aprovação humana).
-- =============================================================================
CREATE TABLE IF NOT EXISTS ai_recommendations (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id            VARCHAR(50) NOT NULL REFERENCES grouping_results(group_id),
    recommendations     TEXT[]      NOT NULL,
    subjects_addressed  TEXT[]      NOT NULL,
    disclaimer          TEXT        NOT NULL,
    model_used          VARCHAR(50) NOT NULL DEFAULT 'mistral',
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_by         VARCHAR(100),                     -- usuário que aprovou (não é PII de aluno)
    approved_at         TIMESTAMPTZ,
    tenant_id           VARCHAR(50) NOT NULL DEFAULT 'school_mvp'
);

-- =============================================================================
-- TABELA: audit_logs
-- Registro imutável de auditoria LGPD.
-- NUNCA atualize ou delete registros desta tabela em produção.
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id    VARCHAR(100) NOT NULL UNIQUE,
    event_type  VARCHAR(100) NOT NULL,
    actor       VARCHAR(100) NOT NULL,
    tenant_id   VARCHAR(50)  NOT NULL DEFAULT 'school_mvp',
    timestamp   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    details     JSONB        NOT NULL DEFAULT '{}'::JSONB
    -- NÃO adicione colunas com PII aqui
);

CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_logs (event_type);
CREATE INDEX IF NOT EXISTS idx_audit_tenant      ON audit_logs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp   ON audit_logs (timestamp DESC);

-- Proteção extra: revogar DELETE/UPDATE na tabela de auditoria
-- (Descomente em produção com usuário admin dedicado)
-- REVOKE DELETE, UPDATE, TRUNCATE ON audit_logs FROM edu_user;

COMMENT ON TABLE grade_records     IS 'LGPD: student_hash = SHA-256[:12]. Sem PII direta.';
COMMENT ON TABLE grouping_results  IS 'Grupos cross-turma sem identificação individual.';
COMMENT ON TABLE ai_recommendations IS 'Recomendações de IA: aprovação humana obrigatória.';
COMMENT ON TABLE audit_logs        IS 'Registro imutável de auditoria. Não deletar/atualizar.';
