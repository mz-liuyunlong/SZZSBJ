-- Walmart keyword V1.1 schema: REVIEW ONLY, no production execution.
-- Requires existing products / product_platform_listings; staged against GitHub main 0054.

CREATE TABLE ai_kw_rule_set (
	rule_key VARCHAR(128) NOT NULL,
	scope_key VARCHAR(128) DEFAULT 'global' NOT NULL,
	rule_type VARCHAR(32) NOT NULL,
	display_name VARCHAR(255) NOT NULL,
	is_enabled BOOLEAN DEFAULT false NOT NULL,
	created_by VARCHAR(255) NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_ai_kw_rule_set PRIMARY KEY (id),
	CONSTRAINT uq_ai_kw_rule_set_rule_key UNIQUE (rule_key, scope_key),
	CONSTRAINT ck_ai_kw_rule_set_type CHECK (rule_type IN ('scoring','search_term_admission','ad_creation','ad_optimization','export'))
);

CREATE TABLE dim_kw_term (
	canonical_keyword TEXT NOT NULL,
	normalized_keyword TEXT NOT NULL,
	translation_default TEXT,
	translation_source VARCHAR(32),
	normalization_version VARCHAR(32) NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_dim_kw_term PRIMARY KEY (id),
	CONSTRAINT uq_dim_kw_term_normalized_keyword UNIQUE (normalized_keyword),
	CONSTRAINT ck_dim_kw_term_nonempty CHECK (length(btrim(normalized_keyword)) > 0)
);

CREATE TABLE raw_kw_asin_snapshot (
	asin VARCHAR(10) NOT NULL,
	fetch_status VARCHAR(16) NOT NULL,
	fetch_provider VARCHAR(64) NOT NULL,
	title TEXT,
	brand TEXT,
	features_json JSONB DEFAULT '[]'::jsonb NOT NULL,
	description_text TEXT,
	raw_object_key TEXT,
	response_hash VARCHAR(64),
	fetched_at TIMESTAMP WITH TIME ZONE,
	error_code VARCHAR(128),
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_raw_kw_asin_snapshot PRIMARY KEY (id),
	CONSTRAINT uq_raw_kw_asin_snapshot_source_account_ref UNIQUE (source_account_ref, id),
	CONSTRAINT ck_raw_kw_asin_snapshot_asin CHECK (asin ~ '^[A-Z0-9]{10}$'),
	CONSTRAINT ck_raw_kw_asin_snapshot_fetch_status CHECK (fetch_status IN ('succeeded','partial','failed'))
);

CREATE TABLE ai_kw_rule_version (
	rule_set_id UUID NOT NULL,
	version_number INTEGER NOT NULL,
	status VARCHAR(16) DEFAULT 'draft' NOT NULL,
	config_json JSONB NOT NULL,
	config_sha256 VARCHAR(64) NOT NULL,
	schema_version VARCHAR(64) NOT NULL,
	engine_version VARCHAR(64) NOT NULL,
	published_by VARCHAR(255),
	published_at TIMESTAMP WITH TIME ZONE,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_ai_kw_rule_version PRIMARY KEY (id),
	CONSTRAINT uq_ai_kw_rule_version_rule_set_id UNIQUE (rule_set_id, version_number),
	CONSTRAINT ck_ai_kw_rule_version_status CHECK (status IN ('draft','published','retired')),
	CONSTRAINT ck_ai_kw_rule_version_published CHECK (status <> 'published' OR (published_by IS NOT NULL AND published_at IS NOT NULL)),
	CONSTRAINT fk_ai_kw_rule_version_rule_set_id_ai_kw_rule_set FOREIGN KEY(rule_set_id) REFERENCES ai_kw_rule_set (id) ON DELETE RESTRICT
);

CREATE TABLE biz_kw_source_event (
	product_id UUID NOT NULL,
	term_id UUID NOT NULL,
	source_kind VARCHAR(32) NOT NULL,
	source_event_key VARCHAR(255) NOT NULL,
	source_reference TEXT,
	store_id VARCHAR(128),
	evidence_json JSONB NOT NULL,
	discovered_at TIMESTAMP WITH TIME ZONE NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_biz_kw_source_event PRIMARY KEY (id),
	CONSTRAINT uq_biz_kw_source_event_source_account_ref UNIQUE (source_account_ref, id),
	CONSTRAINT uq_biz_kw_source_event_source_account_ref UNIQUE (source_account_ref, source_kind, source_event_key, product_id, term_id),
	CONSTRAINT ck_biz_kw_source_event_kind CHECK (source_kind IN ('excel','operator_manual','auto_search_term','system_ad','amazon_text','other')),
	CONSTRAINT fk_biz_kw_source_event_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT,
	CONSTRAINT fk_biz_kw_source_event_term_id_dim_kw_term FOREIGN KEY(term_id) REFERENCES dim_kw_term (id) ON DELETE RESTRICT
);

CREATE TABLE biz_sku_asin_reference (
	product_id UUID NOT NULL,
	asin VARCHAR(10) NOT NULL,
	reference_role VARCHAR(32) DEFAULT 'competitor' NOT NULL,
	is_active BOOLEAN DEFAULT true NOT NULL,
	latest_snapshot_id UUID,
	selected_by VARCHAR(255) NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_biz_sku_asin_reference PRIMARY KEY (id),
	CONSTRAINT fk_biz_sku_asin_reference_source_account_ref_raw_kw_asi_f34b FOREIGN KEY(source_account_ref, latest_snapshot_id) REFERENCES raw_kw_asin_snapshot (source_account_ref, id) ON DELETE RESTRICT,
	CONSTRAINT uq_biz_sku_asin_reference_product_id UNIQUE (product_id, asin, reference_role),
	CONSTRAINT ck_biz_sku_asin_reference_asin CHECK (asin ~ '^[A-Z0-9]{10}$'),
	CONSTRAINT fk_biz_sku_asin_reference_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT
);

CREATE TABLE biz_sku_keyword (
	product_id UUID NOT NULL,
	term_id UUID NOT NULL,
	status VARCHAR(16) DEFAULT 'review' NOT NULL,
	manual_translation TEXT,
	operator_note TEXT,
	confirmed_by VARCHAR(255),
	updated_at TIMESTAMP WITH TIME ZONE,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_biz_sku_keyword PRIMARY KEY (id),
	CONSTRAINT uq_biz_sku_keyword_product_id UNIQUE (product_id, term_id),
	CONSTRAINT uq_biz_sku_keyword_source_account_ref UNIQUE (source_account_ref, id),
	CONSTRAINT ck_biz_sku_keyword_status CHECK (status IN ('active','review','paused','excluded')),
	CONSTRAINT fk_biz_sku_keyword_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT,
	CONSTRAINT fk_biz_sku_keyword_term_id_dim_kw_term FOREIGN KEY(term_id) REFERENCES dim_kw_term (id) ON DELETE RESTRICT
);

CREATE TABLE raw_kw_asin_image (
	asin_snapshot_id UUID NOT NULL,
	image_index INTEGER NOT NULL,
	image_url TEXT NOT NULL,
	image_type VARCHAR(64),
	source_image_id VARCHAR(255),
	width INTEGER,
	height INTEGER,
	url_hash VARCHAR(64),
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_raw_kw_asin_image PRIMARY KEY (id),
	CONSTRAINT fk_raw_kw_asin_image_source_account_ref_raw_kw_asin_snapshot FOREIGN KEY(source_account_ref, asin_snapshot_id) REFERENCES raw_kw_asin_snapshot (source_account_ref, id) ON DELETE RESTRICT,
	CONSTRAINT uq_raw_kw_asin_image_asin_snapshot_id UNIQUE (asin_snapshot_id, image_index),
	CONSTRAINT ck_raw_kw_asin_image_index CHECK (image_index >= 0),
	CONSTRAINT ck_raw_kw_asin_image_width CHECK (width IS NULL OR width > 0),
	CONSTRAINT ck_raw_kw_asin_image_height CHECK (height IS NULL OR height > 0)
);

CREATE TABLE raw_kw_upload_file (
	product_id UUID NOT NULL,
	original_filename TEXT NOT NULL,
	object_key TEXT NOT NULL,
	mime_type VARCHAR(128),
	sha256 VARCHAR(64) NOT NULL,
	file_size_bytes BIGINT NOT NULL,
	parser_version VARCHAR(64),
	status VARCHAR(16) DEFAULT 'uploaded' NOT NULL,
	uploaded_by VARCHAR(255) NOT NULL,
	error_code VARCHAR(100),
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_raw_kw_upload_file PRIMARY KEY (id),
	CONSTRAINT uq_raw_kw_upload_file_source_account_ref UNIQUE (source_account_ref, id),
	CONSTRAINT ck_raw_kw_upload_file_positive_size CHECK (file_size_bytes > 0),
	CONSTRAINT ck_raw_kw_upload_file_sha256 CHECK (sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_raw_kw_upload_file_status CHECK (status IN ('uploaded','parsing','parsed','failed')),
	CONSTRAINT fk_raw_kw_upload_file_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT
);

CREATE TABLE raw_kw_walmart_page_snapshot (
	product_id UUID NOT NULL,
	listing_id UUID,
	store_id VARCHAR(128),
	item_id VARCHAR(128) NOT NULL,
	verification_status VARCHAR(16) NOT NULL,
	fetch_provider VARCHAR(64) NOT NULL,
	provider_observed_at TIMESTAMP WITH TIME ZONE,
	page_title TEXT,
	description_text TEXT,
	features_json JSONB DEFAULT '[]'::jsonb NOT NULL,
	attributes_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	page_images_json JSONB DEFAULT '[]'::jsonb NOT NULL,
	raw_object_key TEXT,
	evidence_hash VARCHAR(64),
	error_code VARCHAR(128),
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_raw_kw_walmart_page_snapshot PRIMARY KEY (id),
	CONSTRAINT uq_raw_kw_walmart_page_snapshot_source_account_ref UNIQUE (source_account_ref, id),
	CONSTRAINT ck_raw_kw_walmart_page_verification CHECK (verification_status IN ('verified','partial','failed','mismatch')),
	CONSTRAINT fk_raw_kw_walmart_page_snapshot_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT,
	CONSTRAINT fk_raw_kw_walmart_page_snapshot_listing_id_product_plat_427d FOREIGN KEY(listing_id) REFERENCES product_platform_listings (id) ON DELETE RESTRICT
);

CREATE TABLE ai_kw_product_fact_snapshot (
	product_id UUID NOT NULL,
	walmart_page_snapshot_id UUID,
	item_id VARCHAR(128) NOT NULL,
	item_verified BOOLEAN DEFAULT false NOT NULL,
	status VARCHAR(16) DEFAULT 'draft' NOT NULL,
	facts_with_sources_json JSONB NOT NULL,
	facts_sha256 VARCHAR(64),
	missing_required_json JSONB DEFAULT '[]'::jsonb NOT NULL,
	confirmed_by VARCHAR(255),
	confirmed_at TIMESTAMP WITH TIME ZONE,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_ai_kw_product_fact_snapshot PRIMARY KEY (id),
	CONSTRAINT uq_ai_kw_product_fact_snapshot_source_account_ref UNIQUE (source_account_ref, id),
	CONSTRAINT fk_ai_kw_product_fact_snapshot_source_account_ref_raw_k_c215 FOREIGN KEY(source_account_ref, walmart_page_snapshot_id) REFERENCES raw_kw_walmart_page_snapshot (source_account_ref, id) ON DELETE RESTRICT,
	CONSTRAINT ck_ai_kw_product_fact_snapshot_status CHECK (status IN ('draft','confirmed','invalid')),
	CONSTRAINT ck_ai_kw_product_fact_snapshot_confirmed CHECK (status <> 'confirmed' OR (confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL AND item_verified IS TRUE AND missing_required_json = '[]'::jsonb)),
	CONSTRAINT fk_ai_kw_product_fact_snapshot_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT
);

CREATE TABLE ai_kw_rule_evaluation (
	product_id UUID,
	term_id UUID,
	source_event_id UUID,
	rule_version_id UUID NOT NULL,
	idempotency_key VARCHAR(255) NOT NULL,
	candidate_keyword TEXT NOT NULL,
	metric_window_start TIMESTAMP WITH TIME ZONE,
	metric_window_end TIMESTAMP WITH TIME ZONE,
	input_metrics_json JSONB NOT NULL,
	decision VARCHAR(16) NOT NULL,
	reason_codes_json JSONB DEFAULT '[]'::jsonb NOT NULL,
	evaluated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_ai_kw_rule_evaluation PRIMARY KEY (id),
	CONSTRAINT fk_ai_kw_rule_evaluation_source_account_ref_biz_kw_source_event FOREIGN KEY(source_account_ref, source_event_id) REFERENCES biz_kw_source_event (source_account_ref, id) ON DELETE RESTRICT,
	CONSTRAINT uq_ai_kw_rule_evaluation_source_account_ref UNIQUE (source_account_ref, idempotency_key),
	CONSTRAINT ck_ai_kw_rule_evaluation_decision CHECK (decision IN ('admit','reject','review','skip')),
	CONSTRAINT fk_ai_kw_rule_evaluation_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT,
	CONSTRAINT fk_ai_kw_rule_evaluation_term_id_dim_kw_term FOREIGN KEY(term_id) REFERENCES dim_kw_term (id) ON DELETE RESTRICT,
	CONSTRAINT fk_ai_kw_rule_evaluation_rule_version_id_ai_kw_rule_version FOREIGN KEY(rule_version_id) REFERENCES ai_kw_rule_version (id) ON DELETE RESTRICT
);

CREATE TABLE biz_kw_decision_history (
	sku_keyword_id UUID NOT NULL,
	rule_version_id UUID,
	action_type VARCHAR(64) NOT NULL,
	before_state_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	after_state_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	reason_code VARCHAR(128) NOT NULL,
	actor_type VARCHAR(32) NOT NULL,
	actor_ref VARCHAR(255) NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_biz_kw_decision_history PRIMARY KEY (id),
	CONSTRAINT fk_biz_kw_decision_history_source_account_ref_biz_sku_keyword FOREIGN KEY(source_account_ref, sku_keyword_id) REFERENCES biz_sku_keyword (source_account_ref, id) ON DELETE RESTRICT,
	CONSTRAINT fk_biz_kw_decision_history_rule_version_id_ai_kw_rule_version FOREIGN KEY(rule_version_id) REFERENCES ai_kw_rule_version (id) ON DELETE RESTRICT
);

CREATE TABLE raw_kw_upload_row (
	upload_id UUID NOT NULL,
	sheet_name VARCHAR(255) NOT NULL,
	row_number INTEGER NOT NULL,
	source_cells JSONB NOT NULL,
	keyword_raw TEXT,
	keyword_normalized TEXT,
	parse_errors JSONB DEFAULT '[]'::jsonb NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_raw_kw_upload_row PRIMARY KEY (id),
	CONSTRAINT uq_raw_kw_upload_row_source_account_ref UNIQUE (source_account_ref, id),
	CONSTRAINT fk_raw_kw_upload_row_source_account_ref_raw_kw_upload_file FOREIGN KEY(source_account_ref, upload_id) REFERENCES raw_kw_upload_file (source_account_ref, id) ON DELETE RESTRICT,
	CONSTRAINT uq_raw_kw_upload_row_upload_id UNIQUE (upload_id, sheet_name, row_number),
	CONSTRAINT ck_raw_kw_upload_row_number CHECK (row_number >= 1)
);

CREATE TABLE ai_kw_analysis_run (
	product_id UUID NOT NULL,
	item_id VARCHAR(128) NOT NULL,
	store_id VARCHAR(128),
	product_fact_snapshot_id UUID NOT NULL,
	walmart_page_snapshot_id UUID,
	rule_version_id UUID NOT NULL,
	status VARCHAR(16) DEFAULT 'queued' NOT NULL,
	request_key VARCHAR(255) NOT NULL,
	input_sha256 VARCHAR(64) NOT NULL,
	engine_version VARCHAR(64) NOT NULL,
	parser_version VARCHAR(64) NOT NULL,
	normalizer_version VARCHAR(64) NOT NULL,
	model_version VARCHAR(128),
	prompt_version VARCHAR(128),
	requested_by VARCHAR(255) NOT NULL,
	confirmed_input_sha256 VARCHAR(64),
	confirmed_by VARCHAR(255),
	confirmed_at TIMESTAMP WITH TIME ZONE,
	started_at TIMESTAMP WITH TIME ZONE,
	finished_at TIMESTAMP WITH TIME ZONE,
	summary_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	error_code VARCHAR(128),
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_ai_kw_analysis_run PRIMARY KEY (id),
	CONSTRAINT uq_ai_kw_analysis_run_source_account_ref UNIQUE (source_account_ref, id),
	CONSTRAINT fk_ai_kw_analysis_run_source_account_ref_ai_kw_product__662d FOREIGN KEY(source_account_ref, product_fact_snapshot_id) REFERENCES ai_kw_product_fact_snapshot (source_account_ref, id) ON DELETE RESTRICT,
	CONSTRAINT fk_ai_kw_analysis_run_source_account_ref_raw_kw_walmart_c6bd FOREIGN KEY(source_account_ref, walmart_page_snapshot_id) REFERENCES raw_kw_walmart_page_snapshot (source_account_ref, id) ON DELETE RESTRICT,
	CONSTRAINT uq_ai_kw_analysis_run_source_account_ref UNIQUE (source_account_ref, request_key),
	CONSTRAINT ck_ai_kw_analysis_run_status CHECK (status IN ('queued','running','succeeded','failed','blocked')),
	CONSTRAINT fk_ai_kw_analysis_run_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT,
	CONSTRAINT fk_ai_kw_analysis_run_rule_version_id_ai_kw_rule_version FOREIGN KEY(rule_version_id) REFERENCES ai_kw_rule_version (id) ON DELETE RESTRICT
);

CREATE TABLE biz_kw_market_observation (
	product_id UUID NOT NULL,
	term_id UUID NOT NULL,
	upload_row_id UUID,
	source_kind VARCHAR(32) NOT NULL,
	observed_date TIMESTAMP WITH TIME ZONE,
	monthly_searches BIGINT,
	monthly_purchases BIGINT,
	ppc_usd NUMERIC(18, 6),
	bid_min_usd NUMERIC(18, 6),
	bid_max_usd NUMERIC(18, 6),
	source_metrics_json JSONB NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_biz_kw_market_observation PRIMARY KEY (id),
	CONSTRAINT fk_biz_kw_market_observation_source_account_ref_raw_kw__7424 FOREIGN KEY(source_account_ref, upload_row_id) REFERENCES raw_kw_upload_row (source_account_ref, id) ON DELETE RESTRICT,
	CONSTRAINT uq_biz_kw_market_observation_upload_row_id UNIQUE (upload_row_id),
	CONSTRAINT ck_biz_kw_observation_searches CHECK (monthly_searches IS NULL OR monthly_searches >= 0),
	CONSTRAINT ck_biz_kw_observation_purchases CHECK (monthly_purchases IS NULL OR monthly_purchases >= 0),
	CONSTRAINT fk_biz_kw_market_observation_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT,
	CONSTRAINT fk_biz_kw_market_observation_term_id_dim_kw_term FOREIGN KEY(term_id) REFERENCES dim_kw_term (id) ON DELETE RESTRICT
);

CREATE TABLE ai_kw_export_file (
	run_id UUID NOT NULL,
	export_kind VARCHAR(32) NOT NULL,
	template_version VARCHAR(64) NOT NULL,
	file_name TEXT NOT NULL,
	object_key TEXT NOT NULL,
	file_sha256 VARCHAR(64) NOT NULL,
	generated_by VARCHAR(255) NOT NULL,
	approved_by VARCHAR(255),
	approved_at TIMESTAMP WITH TIME ZONE,
	original_run_input_sha256 VARCHAR(64) NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_ai_kw_export_file PRIMARY KEY (id),
	CONSTRAINT fk_ai_kw_export_file_source_account_ref_ai_kw_analysis_run FOREIGN KEY(source_account_ref, run_id) REFERENCES ai_kw_analysis_run (source_account_ref, id) ON DELETE RESTRICT,
	CONSTRAINT ck_ai_kw_export_file_sha256 CHECK (file_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE TABLE ai_kw_listing_version (
	run_id UUID NOT NULL,
	version_number INTEGER NOT NULL,
	status VARCHAR(16) NOT NULL,
	title TEXT,
	features_json JSONB DEFAULT '[]'::jsonb NOT NULL,
	description_text TEXT,
	edited_by VARCHAR(255) NOT NULL,
	evidence_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_ai_kw_listing_version PRIMARY KEY (id),
	CONSTRAINT uq_ai_kw_listing_version_run_id UNIQUE (run_id, version_number),
	CONSTRAINT fk_ai_kw_listing_version_source_account_ref_ai_kw_analysis_run FOREIGN KEY(source_account_ref, run_id) REFERENCES ai_kw_analysis_run (source_account_ref, id) ON DELETE RESTRICT
);

CREATE TABLE ai_kw_run_asin (
	run_id UUID NOT NULL,
	asin_snapshot_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_ai_kw_run_asin PRIMARY KEY (id),
	CONSTRAINT fk_ai_kw_run_asin_source_account_ref_ai_kw_analysis_run FOREIGN KEY(source_account_ref, run_id) REFERENCES ai_kw_analysis_run (source_account_ref, id) ON DELETE RESTRICT,
	CONSTRAINT fk_ai_kw_run_asin_source_account_ref_raw_kw_asin_snapshot FOREIGN KEY(source_account_ref, asin_snapshot_id) REFERENCES raw_kw_asin_snapshot (source_account_ref, id) ON DELETE RESTRICT,
	CONSTRAINT uq_ai_kw_run_asin_run_id UNIQUE (run_id, asin_snapshot_id)
);

CREATE TABLE ai_kw_run_file (
	run_id UUID NOT NULL,
	upload_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_ai_kw_run_file PRIMARY KEY (id),
	CONSTRAINT fk_ai_kw_run_file_source_account_ref_ai_kw_analysis_run FOREIGN KEY(source_account_ref, run_id) REFERENCES ai_kw_analysis_run (source_account_ref, id) ON DELETE RESTRICT,
	CONSTRAINT fk_ai_kw_run_file_source_account_ref_raw_kw_upload_file FOREIGN KEY(source_account_ref, upload_id) REFERENCES raw_kw_upload_file (source_account_ref, id) ON DELETE RESTRICT,
	CONSTRAINT uq_ai_kw_run_file_run_id UNIQUE (run_id, upload_id)
);

CREATE TABLE ai_kw_run_keyword (
	run_id UUID NOT NULL,
	term_id UUID NOT NULL,
	keyword_primary_type VARCHAR(64),
	auxiliary_types_json JSONB DEFAULT '[]'::jsonb NOT NULL,
	core_root TEXT,
	root_grade VARCHAR(32),
	page_coverage VARCHAR(64),
	page_evidence_json JSONB DEFAULT '[]'::jsonb NOT NULL,
	component_evidence_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	match_points INTEGER,
	intent_points INTEGER,
	page_points INTEGER,
	root_points INTEGER,
	data_points INTEGER,
	risk_points INTEGER,
	score INTEGER,
	base_grade VARCHAR(32),
	allocation_grade VARCHAR(32),
	hard_risk BOOLEAN DEFAULT false NOT NULL,
	risk_reasons_json JSONB DEFAULT '[]'::jsonb NOT NULL,
	exact_selected BOOLEAN DEFAULT false NOT NULL,
	broad_selected BOOLEAN DEFAULT false NOT NULL,
	broad_role VARCHAR(32),
	exact_reason TEXT,
	broad_reason TEXT,
	quality_note TEXT,
	suggested_optimization_bid NUMERIC(18, 6),
	rank_index INTEGER,
	decision_status VARCHAR(32) NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	source_account_ref VARCHAR(128) NOT NULL,
	CONSTRAINT pk_ai_kw_run_keyword PRIMARY KEY (id),
	CONSTRAINT fk_ai_kw_run_keyword_source_account_ref_ai_kw_analysis_run FOREIGN KEY(source_account_ref, run_id) REFERENCES ai_kw_analysis_run (source_account_ref, id) ON DELETE RESTRICT,
	CONSTRAINT uq_ai_kw_run_keyword_run_id UNIQUE (run_id, term_id),
	CONSTRAINT ck_ai_kw_run_keyword_score CHECK (score IS NULL OR score BETWEEN 0 AND 100),
	CONSTRAINT ck_ai_kw_run_keyword_match_points CHECK (match_points IS NULL OR match_points BETWEEN 0 AND 30),
	CONSTRAINT ck_ai_kw_run_keyword_intent_points CHECK (intent_points IS NULL OR intent_points BETWEEN 0 AND 20),
	CONSTRAINT ck_ai_kw_run_keyword_page_points CHECK (page_points IS NULL OR page_points BETWEEN 0 AND 20),
	CONSTRAINT ck_ai_kw_run_keyword_root_points CHECK (root_points IS NULL OR root_points BETWEEN 0 AND 15),
	CONSTRAINT ck_ai_kw_run_keyword_data_points CHECK (data_points IS NULL OR data_points BETWEEN 0 AND 15),
	CONSTRAINT ck_ai_kw_run_keyword_risk_points CHECK (risk_points IS NULL OR risk_points BETWEEN -40 AND 0),
	CONSTRAINT ck_ai_kw_run_keyword_hard_risk_block CHECK (NOT hard_risk OR (NOT exact_selected AND NOT broad_selected)),
	CONSTRAINT ck_ai_kw_run_keyword_ad_selection_requires_score CHECK (NOT (exact_selected OR broad_selected) OR (score IS NOT NULL AND allocation_grade IN ('P0','P1','P2'))),
	CONSTRAINT ck_ai_kw_run_keyword_broad_role CHECK (NOT broad_selected OR broad_role IN ('root','long_tail')),
	CONSTRAINT fk_ai_kw_run_keyword_term_id_dim_kw_term FOREIGN KEY(term_id) REFERENCES dim_kw_term (id) ON DELETE RESTRICT
);

CREATE INDEX ix_raw_kw_asin_history ON raw_kw_asin_snapshot (source_account_ref, asin, created_at);

CREATE INDEX ix_biz_kw_source_event_sku ON biz_kw_source_event (product_id, term_id, created_at);

CREATE INDEX ix_biz_sku_keyword_product ON biz_sku_keyword (source_account_ref, product_id);

CREATE INDEX ix_raw_kw_upload_file_sku_created ON raw_kw_upload_file (product_id, created_at);

CREATE INDEX ix_raw_kw_walmart_page_lookup ON raw_kw_walmart_page_snapshot (source_account_ref, item_id, created_at);

CREATE INDEX ix_ai_kw_facts_product ON ai_kw_product_fact_snapshot (source_account_ref, product_id, created_at);

CREATE INDEX ix_ai_kw_rule_evaluation_sku ON ai_kw_rule_evaluation (product_id, created_at);

CREATE INDEX ix_biz_kw_decision_history_sku ON biz_kw_decision_history (sku_keyword_id, created_at);

CREATE INDEX ix_raw_kw_upload_row_account_upload ON raw_kw_upload_row (source_account_ref, upload_id);

CREATE INDEX ix_ai_kw_analysis_run_sku_time ON ai_kw_analysis_run (source_account_ref, product_id, created_at);

CREATE INDEX ix_biz_kw_observation_product_term ON biz_kw_market_observation (product_id, term_id, created_at);

CREATE INDEX ix_ai_kw_export_file_run ON ai_kw_export_file (run_id, created_at);

CREATE INDEX ix_ai_kw_run_keyword_run_rank ON ai_kw_run_keyword (run_id, rank_index);

-- Immutable source and published/finalized data guards.

CREATE FUNCTION kw_guard_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'KW_IMMUTABLE_SOURCE: %', TG_TABLE_NAME;
END
$$;

CREATE FUNCTION kw_guard_upload_file() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'KW_UPLOAD_DELETE_FORBIDDEN'; END IF;
    IF (OLD.source_account_ref,OLD.product_id,OLD.original_filename,OLD.object_key,OLD.sha256,
        OLD.file_size_bytes,OLD.uploaded_by,OLD.created_at)
       IS DISTINCT FROM
       (NEW.source_account_ref,NEW.product_id,NEW.original_filename,NEW.object_key,NEW.sha256,
        NEW.file_size_bytes,NEW.uploaded_by,NEW.created_at) THEN
        RAISE EXCEPTION 'KW_UPLOAD_ORIGINAL_CANNOT_CHANGE';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION kw_guard_finalized_status() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'KW_FINALIZED_RECORD_DELETE_FORBIDDEN'; END IF;
    IF TG_TABLE_NAME = 'ai_kw_product_fact_snapshot' AND OLD.status = 'confirmed' THEN
        RAISE EXCEPTION 'KW_CONFIRMED_FACT_IMMUTABLE';
    ELSIF TG_TABLE_NAME = 'ai_kw_rule_version' AND OLD.status IN ('published','retired') THEN
        RAISE EXCEPTION 'KW_PUBLISHED_RULE_IMMUTABLE';
    ELSIF TG_TABLE_NAME = 'ai_kw_analysis_run' AND OLD.status IN ('succeeded','failed','blocked') THEN
        RAISE EXCEPTION 'KW_FINISHED_RUN_IMMUTABLE';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_kw_upload_file_guard BEFORE UPDATE OR DELETE ON raw_kw_upload_file FOR EACH ROW EXECUTE FUNCTION kw_guard_upload_file();

CREATE TRIGGER trg_raw_kw_upload_row_immutable BEFORE UPDATE OR DELETE ON raw_kw_upload_row FOR EACH ROW EXECUTE FUNCTION kw_guard_immutable();

CREATE TRIGGER trg_raw_kw_walmart_page_snapshot_immutable BEFORE UPDATE OR DELETE ON raw_kw_walmart_page_snapshot FOR EACH ROW EXECUTE FUNCTION kw_guard_immutable();

CREATE TRIGGER trg_raw_kw_asin_snapshot_immutable BEFORE UPDATE OR DELETE ON raw_kw_asin_snapshot FOR EACH ROW EXECUTE FUNCTION kw_guard_immutable();

CREATE TRIGGER trg_raw_kw_asin_image_immutable BEFORE UPDATE OR DELETE ON raw_kw_asin_image FOR EACH ROW EXECUTE FUNCTION kw_guard_immutable();

CREATE TRIGGER trg_biz_kw_market_observation_immutable BEFORE UPDATE OR DELETE ON biz_kw_market_observation FOR EACH ROW EXECUTE FUNCTION kw_guard_immutable();

CREATE TRIGGER trg_biz_kw_source_event_immutable BEFORE UPDATE OR DELETE ON biz_kw_source_event FOR EACH ROW EXECUTE FUNCTION kw_guard_immutable();

CREATE TRIGGER trg_ai_kw_run_file_immutable BEFORE UPDATE OR DELETE ON ai_kw_run_file FOR EACH ROW EXECUTE FUNCTION kw_guard_immutable();

CREATE TRIGGER trg_ai_kw_run_asin_immutable BEFORE UPDATE OR DELETE ON ai_kw_run_asin FOR EACH ROW EXECUTE FUNCTION kw_guard_immutable();

CREATE TRIGGER trg_ai_kw_run_keyword_immutable BEFORE UPDATE OR DELETE ON ai_kw_run_keyword FOR EACH ROW EXECUTE FUNCTION kw_guard_immutable();

CREATE TRIGGER trg_ai_kw_export_file_immutable BEFORE UPDATE OR DELETE ON ai_kw_export_file FOR EACH ROW EXECUTE FUNCTION kw_guard_immutable();

CREATE TRIGGER trg_biz_kw_decision_history_immutable BEFORE UPDATE OR DELETE ON biz_kw_decision_history FOR EACH ROW EXECUTE FUNCTION kw_guard_immutable();

CREATE TRIGGER trg_ai_kw_rule_evaluation_immutable BEFORE UPDATE OR DELETE ON ai_kw_rule_evaluation FOR EACH ROW EXECUTE FUNCTION kw_guard_immutable();

CREATE TRIGGER trg_ai_kw_listing_version_immutable BEFORE UPDATE OR DELETE ON ai_kw_listing_version FOR EACH ROW EXECUTE FUNCTION kw_guard_immutable();

CREATE TRIGGER trg_ai_kw_product_fact_snapshot_finalized BEFORE UPDATE OR DELETE ON ai_kw_product_fact_snapshot FOR EACH ROW EXECUTE FUNCTION kw_guard_finalized_status();

CREATE TRIGGER trg_ai_kw_rule_version_finalized BEFORE UPDATE OR DELETE ON ai_kw_rule_version FOR EACH ROW EXECUTE FUNCTION kw_guard_finalized_status();

CREATE TRIGGER trg_ai_kw_analysis_run_finalized BEFORE UPDATE OR DELETE ON ai_kw_analysis_run FOR EACH ROW EXECUTE FUNCTION kw_guard_finalized_status();
