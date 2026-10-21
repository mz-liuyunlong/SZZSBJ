-- LOCAL szzsbj_dev ONLY; backed up before apply.
SET LOCAL search_path=public;

CREATE TABLE ops_domestic_packing_extra_allocations (
	id UUID NOT NULL, 
	order_id UUID NOT NULL, 
	source_account_ref VARCHAR(128) NOT NULL, 
	warehouse_id VARCHAR(64) NOT NULL, 
	sku VARCHAR(255) NOT NULL, 
	source_publication_id UUID NOT NULL, 
	source_board_id UUID NOT NULL, 
	qty INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_ops_domestic_packing_extra_allocations PRIMARY KEY (id), 
	CONSTRAINT uq_ops_domestic_packing_extra_allocations_order_id UNIQUE (order_id, source_board_id), 
	CONSTRAINT packing_extra_qty CHECK (qty>0), 
	CONSTRAINT fk_ops_domestic_packing_extra_allocations_source_public_d304 FOREIGN KEY(source_publication_id, source_board_id) REFERENCES mart_domestic_inbound_batch_board (publication_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_ops_domestic_packing_extra_allocations_order_id_ops__e22c FOREIGN KEY(order_id) REFERENCES ops_domestic_packing_orders (id) ON DELETE RESTRICT
)

;
CREATE INDEX ix_packing_extra_source ON ops_domestic_packing_extra_allocations (source_account_ref, warehouse_id, source_board_id);
DO $$ DECLARE n integer; target text; BEGIN
 SELECT count(*),min(conname) INTO n,target FROM pg_constraint WHERE conrelid='public.evt_domestic_packing_events'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%event_kind%';
 IF n<>1 THEN RAISE EXCEPTION 'Expected one event-kind check'; END IF;
 EXECUTE format('ALTER TABLE public.evt_domestic_packing_events DROP CONSTRAINT %I',target);
END $$;
ALTER TABLE public.evt_domestic_packing_events ADD CONSTRAINT packing_event_kind_warehouse
CHECK(event_kind IN ('approve','reject','link','void','test','boxes','done','customs','note','unpacked','rebox','ib','sync'));
INSERT INTO public.app_permissions(permission_key,name,group_key,description,permission_type,module_key,page_key,action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
VALUES('action:pmc:domestic-warehouse-board:packing-supplement-ib','登记超发补入库单','pmc','中台独立授权：登记超发补入库单','action','pmc','pmc_domestic_warehouse_board','packing-supplement-ib',NULL,'normal',100030,true,now(),now()) ON CONFLICT(permission_key) DO NOTHING;
INSERT INTO public.app_permissions(permission_key,name,group_key,description,permission_type,module_key,page_key,action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
VALUES('action:pmc:domestic-warehouse-board:packing-supplement-sync','校验超发补入库数据','pmc','中台独立授权：校验超发补入库数据','action','pmc','pmc_domestic_warehouse_board','packing-supplement-sync',NULL,'normal',100031,true,now(),now()) ON CONFLICT(permission_key) DO NOTHING;
