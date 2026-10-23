-- LOCAL DEVELOPMENT ONLY. Approved dev/local schema delta; no Alembic version change.
SET LOCAL search_path = public;

CREATE TABLE ops_domestic_packing_box_sets (
	id UUID NOT NULL, 
	order_id UUID NOT NULL, 
	version INTEGER NOT NULL, 
	total_qty INTEGER NOT NULL, 
	approved_qty_snapshot INTEGER NOT NULL, 
	variance_reason VARCHAR(500), 
	package_snapshot JSONB, 
	product_snapshot_id UUID, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	completed_by VARCHAR(128), 
	actor_uid VARCHAR(128) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_ops_domestic_packing_box_sets PRIMARY KEY (id), 
	CONSTRAINT warehouse_box_version CHECK (version>0), 
	CONSTRAINT warehouse_box_total CHECK (total_qty BETWEEN 1 AND 1000000), 
	CONSTRAINT warehouse_approved_qty CHECK (approved_qty_snapshot BETWEEN 1 AND 1000000), 
	CONSTRAINT warehouse_no_overpack CHECK (total_qty<=approved_qty_snapshot), 
	CONSTRAINT warehouse_variance_reason CHECK (total_qty=approved_qty_snapshot OR (variance_reason IS NOT NULL AND length(trim(variance_reason))>=2)), 
	CONSTRAINT warehouse_completion CHECK ((completed_at IS NULL AND completed_by IS NULL) OR (completed_at IS NOT NULL AND completed_by IS NOT NULL AND total_qty=approved_qty_snapshot)), 
	CONSTRAINT uq_ops_domestic_packing_box_sets_order_id UNIQUE (order_id), 
	CONSTRAINT fk_ops_domestic_packing_box_sets_order_id_ops_domestic__da41 FOREIGN KEY(order_id) REFERENCES ops_domestic_packing_orders (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_ops_domestic_packing_box_sets_product_snapshot_id_dw_4df5 FOREIGN KEY(product_snapshot_id) REFERENCES dwd_lingxing_sku_product_info_snapshots (id) ON DELETE RESTRICT
)

;

CREATE TABLE ops_domestic_packing_box_lines (
	id UUID NOT NULL, 
	box_set_id UUID NOT NULL, 
	line_no INTEGER NOT NULL, 
	box_type VARCHAR(16) NOT NULL, 
	boxes INTEGER NOT NULL, 
	units_per_box INTEGER NOT NULL, 
	length_cm NUMERIC(12, 4) NOT NULL, 
	width_cm NUMERIC(12, 4) NOT NULL, 
	height_cm NUMERIC(12, 4) NOT NULL, 
	gross_weight_kg NUMERIC(12, 4) NOT NULL, 
	CONSTRAINT pk_ops_domestic_packing_box_lines PRIMARY KEY (id), 
	CONSTRAINT uq_ops_domestic_packing_box_lines_box_set_id UNIQUE (box_set_id, line_no), 
	CONSTRAINT warehouse_line_no CHECK (line_no BETWEEN 1 AND 20), 
	CONSTRAINT warehouse_box_type CHECK (box_type IN ('A','B','C','custom')), 
	CONSTRAINT warehouse_line_quantity CHECK (boxes BETWEEN 1 AND 9999 AND units_per_box BETWEEN 1 AND 100000), 
	CONSTRAINT warehouse_box_dimensions CHECK (length_cm BETWEEN 1 AND 300 AND width_cm BETWEEN 1 AND 300 AND height_cm BETWEEN 1 AND 300), 
	CONSTRAINT warehouse_box_weight CHECK (gross_weight_kg BETWEEN 0.01 AND 200), 
	CONSTRAINT fk_ops_domestic_packing_box_lines_box_set_id_ops_domest_efdc FOREIGN KEY(box_set_id) REFERENCES ops_domestic_packing_box_sets (id) ON DELETE RESTRICT
)

;

CREATE TABLE ops_domestic_packing_notes (
	order_id UUID NOT NULL, 
	category VARCHAR(32) NOT NULL, 
	text VARCHAR(500) NOT NULL, 
	resolved BOOLEAN NOT NULL, 
	last_event_id UUID NOT NULL, 
	actor_uid VARCHAR(128) NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_ops_domestic_packing_notes PRIMARY KEY (order_id), 
	CONSTRAINT warehouse_note_category CHECK (category IN ('arrival_incomplete','labels','materials','operations','schedule','quality','other','resolved')), 
	CONSTRAINT warehouse_note_text CHECK (category<>'other' OR length(trim(text))>=2), 
	CONSTRAINT warehouse_note_resolution CHECK (resolved=(category='resolved')), 
	CONSTRAINT fk_ops_domestic_packing_notes_order_id_ops_domestic_pac_0641 FOREIGN KEY(order_id) REFERENCES ops_domestic_packing_orders (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_ops_domestic_packing_notes_last_event_id_evt_domesti_4a01 FOREIGN KEY(last_event_id) REFERENCES evt_domestic_packing_events (id) ON DELETE RESTRICT
)

;
DO $$ DECLARE target text; n integer; BEGIN
 SELECT count(*) INTO n FROM pg_constraint WHERE conrelid='public.evt_domestic_packing_events'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%event_kind%';
 IF n<>1 THEN RAISE EXCEPTION 'Expected exactly one event_kind constraint'; END IF;
 SELECT conname INTO target FROM pg_constraint WHERE conrelid='public.evt_domestic_packing_events'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%event_kind%';
 EXECUTE format('ALTER TABLE public.evt_domestic_packing_events DROP CONSTRAINT %I',target);
END $$;
ALTER TABLE public.evt_domestic_packing_events ADD CONSTRAINT packing_event_kind_warehouse
CHECK (event_kind IN ('approve','reject','link','void','test','boxes','done','customs','note'));
INSERT INTO public.app_permissions
 (permission_key,name,group_key,description,permission_type,module_key,page_key,action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
 VALUES ('action:pmc:domestic-warehouse-board:packing-boxes-save','保存仓库装箱','pmc','保存仓库装箱','action','pmc','pmc_domestic_warehouse_board','packing-boxes-save',NULL,'normal',100024,true,now(),now())
 ON CONFLICT (permission_key) DO NOTHING;
INSERT INTO public.app_permissions
 (permission_key,name,group_key,description,permission_type,module_key,page_key,action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
 VALUES ('action:pmc:domestic-warehouse-board:packing-done','确认打包完成','pmc','确认打包完成','action','pmc','pmc_domestic_warehouse_board','packing-done',NULL,'normal',100025,true,now(),now())
 ON CONFLICT (permission_key) DO NOTHING;
INSERT INTO public.app_permissions
 (permission_key,name,group_key,description,permission_type,module_key,page_key,action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
 VALUES ('action:pmc:domestic-warehouse-board:packing-customs','修改打包报关','pmc','修改打包报关','action','pmc','pmc_domestic_warehouse_board','packing-customs',NULL,'normal',100026,true,now(),now())
 ON CONFLICT (permission_key) DO NOTHING;
INSERT INTO public.app_permissions
 (permission_key,name,group_key,description,permission_type,module_key,page_key,action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
 VALUES ('action:pmc:domestic-warehouse-board:packing-note','填写打包延迟备注','pmc','填写打包延迟备注','action','pmc','pmc_domestic_warehouse_board','packing-note',NULL,'normal',100027,true,now(),now())
 ON CONFLICT (permission_key) DO NOTHING;
