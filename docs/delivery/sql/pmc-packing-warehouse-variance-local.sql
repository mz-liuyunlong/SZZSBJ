-- Local dev warehouse final rules extension. No production changes.
SET LOCAL search_path=public;

CREATE TABLE ops_domestic_packing_variance_cases (
	order_id UUID NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	quantity INTEGER NOT NULL, 
	gap_qty INTEGER, 
	reason_category VARCHAR(32), 
	reason VARCHAR(500), 
	supplemental_ib VARCHAR(128), 
	evidence JSONB NOT NULL, 
	actor_uid VARCHAR(128) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_ops_domestic_packing_variance_cases PRIMARY KEY (order_id), 
	CONSTRAINT packing_variance_kind CHECK (kind IN ('under','over')), 
	CONSTRAINT packing_variance_state CHECK (state IN ('pending','blocked','ready','released','voided','resolved')), 
	CONSTRAINT packing_variance_qty CHECK (quantity>0 AND (gap_qty IS NULL OR gap_qty>=0)), 
	CONSTRAINT fk_ops_domestic_packing_variance_cases_order_id_ops_dom_8c82 FOREIGN KEY(order_id) REFERENCES ops_domestic_packing_orders (id) ON DELETE RESTRICT
)

;

CREATE TABLE ops_domestic_packing_notification_outbox (
	id UUID NOT NULL, 
	order_id UUID NOT NULL, 
	order_version INTEGER NOT NULL, 
	kind VARCHAR(32) NOT NULL, 
	state VARCHAR(32) NOT NULL, 
	payload JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_ops_domestic_packing_notification_outbox PRIMARY KEY (id), 
	CONSTRAINT uq_ops_domestic_packing_notification_outbox_order_id UNIQUE (order_id, order_version, kind), 
	CONSTRAINT packing_notice_state CHECK (state IN ('pending_configuration','cancelled','delivered','failed')), 
	CONSTRAINT fk_ops_domestic_packing_notification_outbox_order_id_op_3c85 FOREIGN KEY(order_id) REFERENCES ops_domestic_packing_orders (id) ON DELETE RESTRICT
)

;
DO $$ DECLARE row record; n integer := 0; BEGIN
 FOR row IN SELECT conname FROM pg_constraint
 WHERE conrelid='public.ops_domestic_packing_box_sets'::regclass AND contype='c'
 AND (pg_get_constraintdef(oid) LIKE '%total_qty <= approved_qty_snapshot%'
 OR pg_get_constraintdef(oid) LIKE '%variance_reason IS NOT NULL%'
 OR pg_get_constraintdef(oid) LIKE '%completed_by IS NOT NULL%') LOOP
   EXECUTE format('ALTER TABLE public.ops_domestic_packing_box_sets DROP CONSTRAINT %I',row.conname);
   n := n+1;
 END LOOP;
 IF n<>3 THEN RAISE EXCEPTION 'Expected three original quantity/completion constraints, found %',n; END IF;
END $$;
ALTER TABLE public.ops_domestic_packing_box_sets ADD CONSTRAINT warehouse_completion_final
CHECK ((completed_at IS NULL AND completed_by IS NULL) OR (completed_at IS NOT NULL AND completed_by IS NOT NULL));
