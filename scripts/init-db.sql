-- PostgreSQL initialization script for gait-analysis
-- Runs once on first container startup

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS gait;
CREATE SCHEMA IF NOT EXISTS logs;

-- Set default search path
ALTER DATABASE gait_analysis SET search_path = gait, public;

-- Create tables
CREATE TABLE IF NOT EXISTS gait.patients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    name VARCHAR(255) NOT NULL,
    age_years INT,
    gender VARCHAR(10),
    height_cm DECIMAL(5, 2),
    mass_kg DECIMAL(5, 2),
    shoe_size VARCHAR(10),
    medical_history TEXT,
    notes TEXT,
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS gait.sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES gait.patients(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    session_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'created',
    -- created | uploaded | processing | complete | needs_rerecord | failed
    notes TEXT
);

CREATE TABLE IF NOT EXISTS gait.videos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES gait.sessions(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    filename VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    -- local disk path (primary copy)
    minio_path TEXT,
    -- object path in the gait-videos MinIO bucket, e.g. "{session_id}/{camera_view}/{filename}"
    camera_view VARCHAR(50) NOT NULL,
    -- 'sagittal', 'posterior', 'plantar'
    file_size_bytes BIGINT,
    duration_sec DECIMAL(10, 2),
    fps DECIMAL(5, 2),
    resolution_w INT,
    resolution_h INT,
    format VARCHAR(20),
    upload_complete BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS gait.profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES gait.sessions(id) ON DELETE CASCADE UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    schema_version VARCHAR(20) NOT NULL DEFAULT 'v1',
    profile_json JSONB NOT NULL,
    confidence_score DECIMAL(3, 2),
    quality_flags JSONB,
    processed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS gait.gait_cycles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_id UUID NOT NULL REFERENCES gait.profiles(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    cycle_number INT NOT NULL,
    foot VARCHAR(1) NOT NULL,
    -- 'L' or 'R'
    frame_start INT,
    frame_end INT,
    duration_ms DECIMAL(8, 2),
    cycle_json JSONB
);

CREATE TABLE IF NOT EXISTS gait.processing_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES gait.sessions(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    celery_task_id VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    -- pending | running | completed | failed
    error_message TEXT,
    processing_time_sec DECIMAL(10, 2)
);

CREATE TABLE IF NOT EXISTS logs.audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    event_type VARCHAR(100) NOT NULL,
    -- profile_read, profile_download, etc.
    user_id VARCHAR(255),
    session_id UUID,
    profile_id UUID,
    details JSONB,
    ip_address INET,
    user_agent TEXT
);

CREATE TABLE IF NOT EXISTS gait.quality_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_id UUID NOT NULL REFERENCES gait.profiles(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(10, 4),
    notes TEXT
);

-- Create indexes for common queries
CREATE INDEX idx_sessions_patient_created ON gait.sessions(patient_id, created_at DESC);
CREATE INDEX idx_videos_session_camera ON gait.videos(session_id, camera_view);
CREATE INDEX idx_profiles_patient_created ON gait.profiles(created_at DESC);
CREATE INDEX idx_audit_logs_profile_id ON logs.audit_logs(profile_id);

-- Enable row-level security (foundation for future permission system)
ALTER TABLE gait.patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE gait.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE gait.profiles ENABLE ROW LEVEL SECURITY;

-- Create audit trigger function
CREATE OR REPLACE FUNCTION gait.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for updated_at
CREATE TRIGGER patients_updated_at
    BEFORE UPDATE ON gait.patients
    FOR EACH ROW
    EXECUTE FUNCTION gait.update_updated_at();

CREATE TRIGGER sessions_updated_at
    BEFORE UPDATE ON gait.sessions
    FOR EACH ROW
    EXECUTE FUNCTION gait.update_updated_at();

CREATE TRIGGER profiles_updated_at
    BEFORE UPDATE ON gait.profiles
    FOR EACH ROW
    EXECUTE FUNCTION gait.update_updated_at();

-- Create function for audit logging
CREATE OR REPLACE FUNCTION logs.log_audit_event(
    p_event_type VARCHAR,
    p_user_id VARCHAR,
    p_session_id UUID,
    p_profile_id UUID,
    p_details JSONB,
    p_ip_address INET DEFAULT NULL,
    p_user_agent TEXT DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    v_log_id UUID;
BEGIN
    INSERT INTO logs.audit_logs (
        event_type, user_id, session_id, profile_id, details, ip_address, user_agent
    ) VALUES (
        p_event_type, p_user_id, p_session_id, p_profile_id, p_details, p_ip_address, p_user_agent
    )
    RETURNING id INTO v_log_id;
    RETURN v_log_id;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT USAGE ON SCHEMA gait TO gait_user;
GRANT USAGE ON SCHEMA logs TO gait_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA gait TO gait_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA logs TO gait_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA gait TO gait_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA logs TO gait_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA gait TO gait_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA logs TO gait_user;

-- Final check
SELECT 'Database initialization complete!' AS status;
