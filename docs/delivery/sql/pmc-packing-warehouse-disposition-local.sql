-- Local-only permission definition and audited disposition event; no user/role grants.
DO $$ DECLARE target text; n integer; BEGIN
 SELECT count(*), min(conname) INTO n,target FROM pg_constraint WHERE conrelid='public.evt_domestic_packing_events'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%event_kind%';
 IF n<>1 THEN RAISE EXCEPTION 'Expected one event kind constraint'; END IF;
 EXECUTE format('ALTER TABLE public.evt_domestic_packing_events DROP CONSTRAINT %I',target);
END $$;
ALTER TABLE public.evt_domestic_packing_events ADD CONSTRAINT packing_event_kind_warehouse
CHECK (event_kind IN ('approve','reject','link','void','test','boxes','done','customs','note','unpacked','rebox'));
INSERT INTO public.app_permissions
(permission_key,name,group_key,description,permission_type,module_key,page_key,action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
VALUES ('action:pmc:domestic-warehouse-board:packing-unpacked-dispose','处置未装数量','pmc','中台处置未装数量，仓库无此权限','action','pmc','pmc_domestic_warehouse_board','packing-unpacked-dispose',NULL,'normal',100028,true,now(),now())
ON CONFLICT (permission_key) DO NOTHING;
INSERT INTO public.app_permissions
(permission_key,name,group_key,description,permission_type,module_key,page_key,action_key,field_key,risk_level,sort_order,is_active,created_at,updated_at)
VALUES ('action:pmc:domestic-warehouse-board:packing-rebox','修改已完成装箱','pmc','修改已完成装箱，须填写原因并重新校验','action','pmc','pmc_domestic_warehouse_board','packing-rebox',NULL,'normal',100029,true,now(),now())
ON CONFLICT (permission_key) DO NOTHING;
