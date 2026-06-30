-- =============================================================================
-- OptiFull - Schema de base de datos
-- Motor: MySQL 8.0+
-- =============================================================================

CREATE DATABASE IF NOT EXISTS optifull
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE optifull;

-- =============================================================================
-- INFRAESTRUCTURA
-- =============================================================================

CREATE TABLE IF NOT EXISTS camaras (
    id          INT             NOT NULL AUTO_INCREMENT PRIMARY KEY,
    nombre      VARCHAR(100)    NOT NULL,
    ubicacion   VARCHAR(255),
    rtsp_url    TEXT            NOT NULL,
    activa      BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at  DATETIME        NOT NULL DEFAULT NOW()
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sesiones_video (
    id              INT         NOT NULL AUTO_INCREMENT PRIMARY KEY,
    camara_id       INT         NOT NULL,
    inicio          DATETIME    NOT NULL,
    fin             DATETIME,
    archivo_path    TEXT,
    duracion_seg    FLOAT       GENERATED ALWAYS AS (
                        TIMESTAMPDIFF(SECOND, inicio, fin)
                    ) STORED,
    FOREIGN KEY (camara_id) REFERENCES camaras(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================================
-- ZONAS DEL LOCAL
-- =============================================================================

CREATE TABLE IF NOT EXISTS zonas (
    id          INT             NOT NULL AUTO_INCREMENT PRIMARY KEY,
    camara_id   INT             NOT NULL,
    nombre      VARCHAR(100)    NOT NULL,
    tipo        ENUM('entrada','salida','caja','gondola','deposito','otro') NOT NULL DEFAULT 'otro',
    poligono    JSON            NOT NULL,
    FOREIGN KEY (camara_id) REFERENCES camaras(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================================
-- PERSONAS Y TRAYECTORIAS
-- =============================================================================

CREATE TABLE IF NOT EXISTS personas (
    id                          INT         NOT NULL AUTO_INCREMENT PRIMARY KEY,
    sesion_id                   INT         NOT NULL,
    primera_deteccion           DATETIME    NOT NULL,
    ultima_deteccion            DATETIME    NOT NULL,
    duracion_total_seg          FLOAT       GENERATED ALWAYS AS (
                                    TIMESTAMPDIFF(SECOND, primera_deteccion, ultima_deteccion)
                                ) STORED,
    comportamiento_sospechoso   BOOLEAN     NOT NULL DEFAULT FALSE,
    FOREIGN KEY (sesion_id) REFERENCES sesiones_video(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS trayectorias (
    id              BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
    persona_id      INT         NOT NULL,
    zona_id         INT,
    timestamp       DATETIME    NOT NULL,
    centroide_x     FLOAT       NOT NULL,
    centroide_y     FLOAT       NOT NULL,
    bbox_x1         FLOAT,
    bbox_y1         FLOAT,
    bbox_x2         FLOAT,
    bbox_y2         FLOAT,
    FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE CASCADE,
    FOREIGN KEY (zona_id)    REFERENCES zonas(id)    ON DELETE SET NULL
) ENGINE=InnoDB;

-- =============================================================================
-- PRODUCTOS Y DETECCIONES
-- =============================================================================

CREATE TABLE IF NOT EXISTS productos (
    id              INT             NOT NULL AUTO_INCREMENT PRIMARY KEY,
    nombre          VARCHAR(255)    NOT NULL,
    codigo          VARCHAR(100)    UNIQUE,
    categoria       VARCHAR(100),
    stock_actual    INT             NOT NULL DEFAULT 0,
    stock_minimo    INT             NOT NULL DEFAULT 0,
    imagen_path     TEXT,
    activo          BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      DATETIME        NOT NULL DEFAULT NOW()
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS detecciones_producto (
    id              BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
    sesion_id       INT         NOT NULL,
    producto_id     INT         NOT NULL,
    timestamp       DATETIME    NOT NULL,
    confianza       FLOAT       NOT NULL,
    cantidad        INT         NOT NULL DEFAULT 1,
    bbox_x1         FLOAT,
    bbox_y1         FLOAT,
    bbox_x2         FLOAT,
    bbox_y2         FLOAT,
    CONSTRAINT chk_confianza CHECK (confianza BETWEEN 0 AND 1),
    FOREIGN KEY (sesion_id)   REFERENCES sesiones_video(id) ON DELETE CASCADE,
    FOREIGN KEY (producto_id) REFERENCES productos(id)      ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================================
-- ALERTAS
-- =============================================================================

CREATE TABLE IF NOT EXISTS alertas (
    id              INT         NOT NULL AUTO_INCREMENT PRIMARY KEY,
    persona_id      INT         NOT NULL,
    tipo            ENUM('salida_sin_pagar','permanencia_excesiva','zona_restringida','otro') NOT NULL,
    timestamp       DATETIME    NOT NULL DEFAULT NOW(),
    descripcion     TEXT,
    resuelta        BOOLEAN     NOT NULL DEFAULT FALSE,
    imagen_path     TEXT,
    FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================================
-- METRICAS AGREGADAS
-- =============================================================================

CREATE TABLE IF NOT EXISTS metricas_flujo (
    id                          INT         NOT NULL AUTO_INCREMENT PRIMARY KEY,
    camara_id                   INT         NOT NULL,
    zona_id                     INT,
    periodo_inicio              DATETIME    NOT NULL,
    periodo_fin                 DATETIME    NOT NULL,
    granularidad                ENUM('hora','dia','semana') NOT NULL,
    personas_unicas             INT         NOT NULL DEFAULT 0,
    personas_max_simultaneas    INT         NOT NULL DEFAULT 0,
    permanencia_promedio_seg    FLOAT,
    tiempo_espera_caja_seg      FLOAT,
    UNIQUE KEY uq_metrica (camara_id, zona_id, periodo_inicio, granularidad),
    FOREIGN KEY (camara_id) REFERENCES camaras(id) ON DELETE CASCADE,
    FOREIGN KEY (zona_id)   REFERENCES zonas(id)   ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mapas_calor (
    id                   INT         NOT NULL AUTO_INCREMENT PRIMARY KEY,
    camara_id            INT         NOT NULL,
    sesion_id            INT,
    periodo_inicio       DATETIME    NOT NULL,
    periodo_fin          DATETIME    NOT NULL,
    granularidad         ENUM('hora','dia','semana') NOT NULL,
    matriz               JSON        NOT NULL,
    resolucion_x         INT         NOT NULL DEFAULT 64,
    resolucion_y         INT         NOT NULL DEFAULT 64,
    imagen_path          TEXT,
    punto_max_x          INT,
    punto_max_y          INT,
    valor_maximo         FLOAT,
    area_activa_pct      FLOAT,
    concentracion        FLOAT,
    zona_id_mas_caliente INT,
    total_detecciones    INT         NOT NULL DEFAULT 0,
    frames_procesados    INT         NOT NULL DEFAULT 0,
    UNIQUE KEY uq_calor (camara_id, periodo_inicio, granularidad),
    FOREIGN KEY (camara_id)            REFERENCES camaras(id)        ON DELETE CASCADE,
    FOREIGN KEY (sesion_id)            REFERENCES sesiones_video(id) ON DELETE SET NULL,
    FOREIGN KEY (zona_id_mas_caliente) REFERENCES zonas(id)          ON DELETE SET NULL
) ENGINE=InnoDB;

-- Para bases de datos existentes, ejecutar:
-- ALTER TABLE mapas_calor
--     ADD COLUMN IF NOT EXISTS sesion_id            INT         AFTER camara_id,
--     ADD COLUMN IF NOT EXISTS imagen_path          TEXT        AFTER resolucion_y,
--     ADD COLUMN IF NOT EXISTS punto_max_x          INT         AFTER imagen_path,
--     ADD COLUMN IF NOT EXISTS punto_max_y          INT         AFTER punto_max_x,
--     ADD COLUMN IF NOT EXISTS valor_maximo         FLOAT       AFTER punto_max_y,
--     ADD COLUMN IF NOT EXISTS area_activa_pct      FLOAT       AFTER valor_maximo,
--     ADD COLUMN IF NOT EXISTS concentracion        FLOAT       AFTER area_activa_pct,
--     ADD COLUMN IF NOT EXISTS zona_id_mas_caliente INT         AFTER concentracion,
--     ADD COLUMN IF NOT EXISTS total_detecciones    INT NOT NULL DEFAULT 0 AFTER zona_id_mas_caliente,
--     ADD COLUMN IF NOT EXISTS frames_procesados    INT NOT NULL DEFAULT 0 AFTER total_detecciones,
--     MODIFY COLUMN resolucion_x INT NOT NULL DEFAULT 64,
--     MODIFY COLUMN resolucion_y INT NOT NULL DEFAULT 64;

-- =============================================================================
-- INDICES
-- =============================================================================

CREATE INDEX idx_trayectorias_persona   ON trayectorias     (persona_id, timestamp);
CREATE INDEX idx_trayectorias_zona      ON trayectorias     (zona_id);
CREATE INDEX idx_trayectorias_ts        ON trayectorias     (timestamp);
CREATE INDEX idx_personas_sesion        ON personas         (sesion_id);
CREATE INDEX idx_personas_sospechosos   ON personas         (comportamiento_sospechoso);
CREATE INDEX idx_det_producto           ON detecciones_producto (producto_id, timestamp);
CREATE INDEX idx_det_sesion             ON detecciones_producto (sesion_id);
CREATE INDEX idx_alertas_no_resueltas   ON alertas          (resuelta);
CREATE INDEX idx_alertas_persona        ON alertas          (persona_id);
CREATE INDEX idx_sesiones_camara        ON sesiones_video   (camara_id, inicio);
CREATE INDEX idx_metricas_periodo       ON metricas_flujo   (camara_id, periodo_inicio, granularidad);
CREATE INDEX idx_calor_periodo          ON mapas_calor      (camara_id, periodo_inicio, granularidad);

-- =============================================================================
-- DATOS INICIALES
-- =============================================================================

INSERT INTO camaras (nombre, ubicacion, rtsp_url) VALUES
    ('Camara Entrada',  'Puerta principal',  'rtsp://192.168.1.10:554/stream1'),
    ('Camara Caja',     'Mostrador de pago', 'rtsp://192.168.1.11:554/stream1'),
    ('Camara Gondolas', 'Pasillo central',   'rtsp://192.168.1.12:554/stream1');

INSERT INTO zonas (camara_id, nombre, tipo, poligono) VALUES
    (1, 'Zona Entrada',  'entrada', '[[0,0],[320,0],[320,480],[0,480]]'),
    (1, 'Zona Caja',     'caja',    '[[320,0],[640,0],[640,480],[320,480]]'),
    (2, 'Frente Caja 1', 'caja',    '[[0,200],[640,200],[640,480],[0,480]]'),
    (3, 'Gondola A',     'gondola', '[[0,0],[640,240],[640,480],[0,480]]');
