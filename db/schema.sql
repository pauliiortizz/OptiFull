-- =============================================================================
-- OptiFull - Schema de base de datos
-- Motor: PostgreSQL 15+ (Supabase)
-- =============================================================================

-- =============================================================================
-- INFRAESTRUCTURA
-- =============================================================================

CREATE TABLE IF NOT EXISTS camaras (
    id          SERIAL          PRIMARY KEY,
    nombre      VARCHAR(100)    NOT NULL,
    ubicacion   VARCHAR(255),
    rtsp_url    TEXT            NOT NULL,
    activa      BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sesiones_video (
    id              SERIAL      PRIMARY KEY,
    camara_id       INT         NOT NULL,
    inicio          TIMESTAMP   NOT NULL,
    fin             TIMESTAMP,
    archivo_path    TEXT,
    frame_w         INT,
    frame_h         INT,
    duracion_seg    FLOAT       GENERATED ALWAYS AS (
                        EXTRACT(EPOCH FROM (fin - inicio))
                    ) STORED,
    FOREIGN KEY (camara_id) REFERENCES camaras(id) ON DELETE CASCADE
);

-- Migracion idempotente para sesiones ya creadas antes de agregar frame_w/h.
-- Sin esto, las coordenadas de 'trayectorias' (en pixeles del frame ORIGINAL
-- del video, no de la foto de fondo que puede tener otra resolucion) no se
-- pueden alinear de forma confiable contra la foto fija del local.
ALTER TABLE sesiones_video ADD COLUMN IF NOT EXISTS frame_w INT;
ALTER TABLE sesiones_video ADD COLUMN IF NOT EXISTS frame_h INT;

-- =============================================================================
-- ZONAS DEL LOCAL
-- =============================================================================

CREATE TABLE IF NOT EXISTS zonas (
    id          SERIAL          PRIMARY KEY,
    camara_id   INT             NOT NULL,
    nombre      VARCHAR(100)    NOT NULL,
    tipo        TEXT            NOT NULL DEFAULT 'otro'
                                CHECK (tipo IN ('entrada','salida','caja','gondola','deposito','otro')),
    poligono    JSONB           NOT NULL,
    FOREIGN KEY (camara_id) REFERENCES camaras(id) ON DELETE CASCADE
);

-- =============================================================================
-- PERSONAS Y TRAYECTORIAS
-- =============================================================================

CREATE TABLE IF NOT EXISTS personas (
    id                          SERIAL      PRIMARY KEY,
    sesion_id                   INT         NOT NULL,
    primera_deteccion           TIMESTAMP   NOT NULL,
    ultima_deteccion            TIMESTAMP   NOT NULL,
    duracion_total_seg          FLOAT       GENERATED ALWAYS AS (
                                    EXTRACT(EPOCH FROM (ultima_deteccion - primera_deteccion))
                                ) STORED,
    comportamiento_sospechoso   BOOLEAN     NOT NULL DEFAULT FALSE,
    metodo_reid                 TEXT        CHECK (metodo_reid IN ('nuevo','posicion','apariencia','gemini','groq')),
    descripcion_visual          TEXT,
    -- Agrupa filas de 'personas' (una fila = una aparicion en UNA sesion/video)
    -- que Gemini identifico como el MISMO cliente real en otra sesion del mismo
    -- dia. Auto-referencia: si es la primera aparicion conocida, cliente_id
    -- apunta a su propio id; si Gemini la reidentifico, apunta al id de la
    -- primera aparicion de esa cadena.
    cliente_id                  INT,
    -- Confirmado a mano (desde el frontend) cuando un cliente_id resulta ser
    -- personal del local y no un visitante -- se marca solo en la fila raiz
    -- (id = cliente_id de la cadena) para que aplique a todas sus apariciones.
    -- La heuristica de "posible empleado" (mucho tiempo total en el local un
    -- mismo dia) solo sugiere candidatos; nunca marca este campo sola.
    es_empleado                 BOOLEAN     NOT NULL DEFAULT FALSE,
    FOREIGN KEY (sesion_id)   REFERENCES sesiones_video(id) ON DELETE CASCADE,
    FOREIGN KEY (cliente_id)  REFERENCES personas(id)       ON DELETE SET NULL
);

-- Migracion idempotente para bases ya creadas antes de agregar 'cliente_id'.
ALTER TABLE personas ADD COLUMN IF NOT EXISTS cliente_id INT REFERENCES personas(id) ON DELETE SET NULL;

-- Migracion idempotente para bases ya creadas antes de agregar 'es_empleado'.
ALTER TABLE personas ADD COLUMN IF NOT EXISTS es_empleado BOOLEAN NOT NULL DEFAULT FALSE;

-- Migracion idempotente para permitir 'groq' como metodo_reid (antes solo 'gemini').
ALTER TABLE personas DROP CONSTRAINT IF EXISTS personas_metodo_reid_check;
ALTER TABLE personas ADD CONSTRAINT personas_metodo_reid_check
    CHECK (metodo_reid IN ('nuevo','posicion','apariencia','gemini','groq'));

CREATE TABLE IF NOT EXISTS trayectorias (
    id              BIGSERIAL   PRIMARY KEY,
    persona_id      INT         NOT NULL,
    zona_id         INT,
    timestamp       TIMESTAMP   NOT NULL,
    centroide_x     FLOAT       NOT NULL,
    centroide_y     FLOAT       NOT NULL,
    bbox_x1         FLOAT,
    bbox_y1         FLOAT,
    bbox_x2         FLOAT,
    bbox_y2         FLOAT,
    FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE CASCADE,
    FOREIGN KEY (zona_id)    REFERENCES zonas(id)    ON DELETE SET NULL
);

-- Un segmento de presencia continua ante camara ("visita"). Se cierra y se
-- abre uno nuevo solo ante huecos LARGOS (reconexion por apariencia dentro
-- del mismo video, o reidentificacion Groq/Gemini) -- los huecos cortos
-- (reconexion por posicion, oclusiones breves) siguen siendo la misma
-- visita. duracion_seg de esta tabla es lo que hay que sumar (agrupando por
-- personas.cliente_id) para obtener el tiempo real de permanencia; NO usar
-- personas.duracion_total_seg para eso, que puede incluir huecos.
CREATE TABLE IF NOT EXISTS visitas (
    id              BIGSERIAL   PRIMARY KEY,
    persona_id      INT         NOT NULL,
    entrada         TIMESTAMP   NOT NULL,
    salida          TIMESTAMP   NOT NULL,
    duracion_seg    FLOAT       GENERATED ALWAYS AS (
                        EXTRACT(EPOCH FROM (salida - entrada))
                    ) STORED,
    FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE CASCADE
);

-- =============================================================================
-- PRODUCTOS Y DETECCIONES
-- =============================================================================

CREATE TABLE IF NOT EXISTS productos (
    id              SERIAL          PRIMARY KEY,
    nombre          VARCHAR(255)    NOT NULL,
    codigo          VARCHAR(100)    UNIQUE,
    categoria       VARCHAR(100),
    stock_actual    INT             NOT NULL DEFAULT 0,
    stock_minimo    INT             NOT NULL DEFAULT 0,
    imagen_path     TEXT,
    activo          BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS detecciones_producto (
    id              BIGSERIAL   PRIMARY KEY,
    sesion_id       INT         NOT NULL,
    producto_id     INT         NOT NULL,
    timestamp       TIMESTAMP   NOT NULL,
    confianza       FLOAT       NOT NULL,
    cantidad        INT         NOT NULL DEFAULT 1,
    bbox_x1         FLOAT,
    bbox_y1         FLOAT,
    bbox_x2         FLOAT,
    bbox_y2         FLOAT,
    CONSTRAINT chk_confianza CHECK (confianza BETWEEN 0 AND 1),
    FOREIGN KEY (sesion_id)   REFERENCES sesiones_video(id) ON DELETE CASCADE,
    FOREIGN KEY (producto_id) REFERENCES productos(id)      ON DELETE CASCADE
);

-- =============================================================================
-- ALERTAS
-- =============================================================================

CREATE TABLE IF NOT EXISTS alertas (
    id              SERIAL      PRIMARY KEY,
    persona_id      INT         NOT NULL,
    tipo            TEXT        NOT NULL
                                CHECK (tipo IN ('salida_sin_pagar','permanencia_excesiva','zona_restringida','otro')),
    timestamp       TIMESTAMP   NOT NULL DEFAULT NOW(),
    descripcion     TEXT,
    resuelta        BOOLEAN     NOT NULL DEFAULT FALSE,
    imagen_path     TEXT,
    FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE CASCADE
);

-- =============================================================================
-- METRICAS AGREGADAS
-- =============================================================================

CREATE TABLE IF NOT EXISTS metricas_flujo (
    id                          SERIAL      PRIMARY KEY,
    camara_id                   INT         NOT NULL,
    zona_id                     INT,
    periodo_inicio              TIMESTAMP   NOT NULL,
    periodo_fin                 TIMESTAMP   NOT NULL,
    granularidad                TEXT        NOT NULL CHECK (granularidad IN ('hora','dia','semana')),
    personas_unicas             INT         NOT NULL DEFAULT 0,
    personas_max_simultaneas    INT         NOT NULL DEFAULT 0,
    permanencia_promedio_seg    FLOAT,
    tiempo_espera_caja_seg      FLOAT,
    CONSTRAINT uq_metrica UNIQUE (camara_id, zona_id, periodo_inicio, granularidad),
    FOREIGN KEY (camara_id) REFERENCES camaras(id) ON DELETE CASCADE,
    FOREIGN KEY (zona_id)   REFERENCES zonas(id)   ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS mapas_calor (
    id                   SERIAL      PRIMARY KEY,
    camara_id            INT         NOT NULL,
    sesion_id            INT,
    periodo_inicio       TIMESTAMP   NOT NULL,
    periodo_fin          TIMESTAMP   NOT NULL,
    granularidad         TEXT        NOT NULL CHECK (granularidad IN ('hora','dia','semana')),
    matriz               JSONB       NOT NULL,
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
    CONSTRAINT uq_calor UNIQUE (camara_id, periodo_inicio, granularidad),
    FOREIGN KEY (camara_id)            REFERENCES camaras(id)        ON DELETE CASCADE,
    FOREIGN KEY (sesion_id)            REFERENCES sesiones_video(id) ON DELETE SET NULL,
    FOREIGN KEY (zona_id_mas_caliente) REFERENCES zonas(id)          ON DELETE SET NULL
);

-- Mapa de calor acumulado por camara: se combinan (sumando, no reemplazando)
-- todas las sesiones de 'mapas_calor' de una misma camara, para tener "el"
-- recorrido historico consolidado de esa camara en una unica fila.
CREATE TABLE IF NOT EXISTS mapas_calor_camara (
    camara_id            INT         PRIMARY KEY,
    matriz               JSONB       NOT NULL,
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
    sesiones_combinadas  INT         NOT NULL DEFAULT 0,
    actualizado_en       TIMESTAMP   NOT NULL DEFAULT NOW(),
    FOREIGN KEY (camara_id)            REFERENCES camaras(id) ON DELETE CASCADE,
    FOREIGN KEY (zona_id_mas_caliente) REFERENCES zonas(id)   ON DELETE SET NULL
);

-- =============================================================================
-- INDICES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_trayectorias_persona   ON trayectorias     (persona_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_trayectorias_zona      ON trayectorias     (zona_id);
CREATE INDEX IF NOT EXISTS idx_trayectorias_ts        ON trayectorias     (timestamp);
CREATE INDEX IF NOT EXISTS idx_visitas_persona        ON visitas          (persona_id);
CREATE INDEX IF NOT EXISTS idx_personas_sesion        ON personas         (sesion_id);
CREATE INDEX IF NOT EXISTS idx_personas_sospechosos   ON personas         (comportamiento_sospechoso);
CREATE INDEX IF NOT EXISTS idx_personas_cliente       ON personas         (cliente_id);
CREATE INDEX IF NOT EXISTS idx_personas_deteccion_dia ON personas         ((primera_deteccion::date));
CREATE INDEX IF NOT EXISTS idx_det_producto           ON detecciones_producto (producto_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_det_sesion             ON detecciones_producto (sesion_id);
CREATE INDEX IF NOT EXISTS idx_alertas_no_resueltas   ON alertas          (resuelta);
CREATE INDEX IF NOT EXISTS idx_alertas_persona        ON alertas          (persona_id);
CREATE INDEX IF NOT EXISTS idx_sesiones_camara        ON sesiones_video   (camara_id, inicio);
CREATE INDEX IF NOT EXISTS idx_metricas_periodo       ON metricas_flujo   (camara_id, periodo_inicio, granularidad);
CREATE INDEX IF NOT EXISTS idx_calor_periodo          ON mapas_calor      (camara_id, periodo_inicio, granularidad);

-- =============================================================================
-- DATOS INICIALES
-- =============================================================================

INSERT INTO camaras (id, nombre, ubicacion, rtsp_url) VALUES
    (1, 'Camara Entrada',  'Puerta principal',  'rtsp://192.168.1.10:554/stream1'),
    (2, 'Camara Caja',     'Mostrador de pago', 'rtsp://192.168.1.11:554/stream1'),
    (3, 'Camara Gondolas', 'Pasillo central',   'rtsp://192.168.1.12:554/stream1')
ON CONFLICT (id) DO NOTHING;

INSERT INTO zonas (id, camara_id, nombre, tipo, poligono) VALUES
    (1, 1, 'Zona Entrada',  'entrada', '[[0,0],[320,0],[320,480],[0,480]]'),
    (2, 1, 'Zona Caja',     'caja',    '[[320,0],[640,0],[640,480],[320,480]]'),
    (3, 2, 'Frente Caja 1', 'caja',    '[[0,200],[640,200],[640,480],[0,480]]'),
    (4, 3, 'Gondola A',     'gondola', '[[0,0],[640,240],[640,480],[0,480]]')
ON CONFLICT (id) DO NOTHING;

-- Los ids de las semillas se insertan a mano (para que ON CONFLICT (id) sea
-- idempotente), asi que hay que sincronizar la secuencia de SERIAL para que
-- el proximo INSERT sin id explicito no choque con estas filas.
SELECT setval('camaras_id_seq', (SELECT MAX(id) FROM camaras));
SELECT setval('zonas_id_seq',   (SELECT MAX(id) FROM zonas));
