import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import "./CustomTagManagerModal.css";

export interface CustomProductTag {
  id: string | number;
  name: string;
  color: string;
  usage: number;
}

export interface CustomProductTagMutation {
  name: string;
  color: string;
}

interface CustomTagManagerModalProps {
  open: boolean;
  onClose: () => void;
  initialTags?: CustomProductTag[];
  loading?: boolean;
  onTagsChange?: (tags: CustomProductTag[]) => void;
  onCreateTag?: (payload: CustomProductTagMutation) => Promise<CustomProductTag>;
  onUpdateTag?: (tagId: string, payload: CustomProductTagMutation) => Promise<CustomProductTag>;
  onDeleteTag?: (tagId: string) => Promise<void>;
}

const MAX_TAG_NAME_LENGTH = 16;

const TAG_COLORS = [
  { name: "蓝", value: "#1677FF" },
  { name: "绿", value: "#16A36A" },
  { name: "青", value: "#13A8A8" },
  { name: "橙", value: "#D99000" },
  { name: "红", value: "#E5484D" },
  { name: "紫", value: "#7C5CFF" },
  { name: "粉", value: "#EB5B9A" },
  { name: "灰", value: "#667085" },
];

const DEFAULT_TAGS: CustomProductTag[] = [
  { id: 1, name: "重点产品", color: "#E5484D", usage: 128 },
  { id: 2, name: "主推", color: "#1677FF", usage: 86 },
  { id: 3, name: "新品", color: "#7C5CFF", usage: 46 },
  { id: 4, name: "高利润", color: "#16A36A", usage: 31 },
  { id: 5, name: "清库存", color: "#D99000", usage: 12 },
  { id: 6, name: "待优化", color: "#667085", usage: 8 },
];

const normalizeTagName = (value: string) => value.trim().replace(/\s+/g, " ");

const isDuplicateTagName = (
  tags: CustomProductTag[],
  name: string,
  exceptId?: CustomProductTag["id"] | null,
) => {
  const normalized = normalizeTagName(name).toLocaleLowerCase();
  return tags.some((tag) => (
    tag.id !== exceptId
    && normalizeTagName(tag.name).toLocaleLowerCase() === normalized
  ));
};

const colorStyle = (color: string) => ({ "--tag-color": color } as CSSProperties);

const nextTagId = (tags: CustomProductTag[]) => {
  const numericIds = tags
    .map((tag) => Number(tag.id))
    .filter((id) => Number.isFinite(id));

  return String((numericIds.length > 0 ? Math.max(...numericIds) : 0) + 1);
};

interface ColorOptionsProps {
  selectedColor: string;
  compact?: boolean;
  onSelect: (color: string) => void;
}

function ColorOptions({ selectedColor, compact = false, onSelect }: ColorOptionsProps) {
  return (
    <div
      className={compact ? "custom-tag-manager__color-row custom-tag-manager__color-row--compact" : "custom-tag-manager__color-row"}
      aria-label="选择标签颜色"
    >
      {TAG_COLORS.map((color, index) => (
        <button
          key={color.value}
          type="button"
          className={color.value === selectedColor
            ? "custom-tag-manager__color-option custom-tag-manager__color-option--selected"
            : "custom-tag-manager__color-option"}
          style={colorStyle(color.value)}
          title={index === 0 ? `${color.name}（默认）` : color.name}
          aria-label={index === 0 ? `${color.name}，默认颜色` : color.name}
          aria-pressed={color.value === selectedColor}
          onClick={() => onSelect(color.value)}
        />
      ))}
    </div>
  );
}

function CustomTagManagerModal({
  open,
  onClose,
  initialTags = DEFAULT_TAGS,
  loading = false,
  onTagsChange,
  onCreateTag,
  onUpdateTag,
  onDeleteTag,
}: CustomTagManagerModalProps) {
  const tags = initialTags;
  const [createName, setCreateName] = useState("");
  const [createColor, setCreateColor] = useState(TAG_COLORS[0].value);
  const [editingId, setEditingId] = useState<CustomProductTag["id"] | null>(null);
  const [editName, setEditName] = useState("");
  const [editColor, setEditColor] = useState(TAG_COLORS[0].value);
  const [deleteId, setDeleteId] = useState<CustomProductTag["id"] | null>(null);
  const [toast, setToast] = useState("");
  const [isMutating, setIsMutating] = useState(false);

  const inputRef = useRef<HTMLInputElement | null>(null);
  const toastTimerRef = useRef<number | null>(null);

  const busy = loading || isMutating;
  const normalizedCreateName = normalizeTagName(createName);
  const createError = normalizedCreateName && isDuplicateTagName(tags, normalizedCreateName)
    ? "已有同名标签，请换一个名称"
    : "";
  const addDisabled = !normalizedCreateName || Boolean(createError) || busy;

  const editingTag = useMemo(
    () => tags.find((tag) => tag.id === editingId),
    [editingId, tags],
  );
  const deleteTag = useMemo(
    () => tags.find((tag) => tag.id === deleteId),
    [deleteId, tags],
  );

  const normalizedEditName = normalizeTagName(editName);
  const editError = editingId == null
    ? ""
    : !normalizedEditName
      ? "标签名称不能为空"
      : isDuplicateTagName(tags, normalizedEditName, editingId)
        ? "已有同名标签"
        : "";
  const saveDisabled = Boolean(editError) || busy;


  useEffect(() => {
    if (!open) return undefined;

    const timer = window.setTimeout(() => {
      inputRef.current?.focus();
    }, 160);

    return () => window.clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    if (!toast) return undefined;

    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => setToast(""), 1500);

    return () => {
      if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
    };
  }, [toast]);

  useEffect(() => {
    if (!open) return undefined;

    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (deleteId != null) {
        setDeleteId(null);
        return;
      }
      if (editingId != null) {
        setEditingId(null);
        return;
      }
      onClose();
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [deleteId, editingId, onClose, open]);

  const commitTags = (updater: (current: CustomProductTag[]) => CustomProductTag[]) => {
    const next = updater(tags);
    onTagsChange?.(next);
  };

  const closeModal = () => {
    setDeleteId(null);
    setEditingId(null);
    onClose();
  };

  const addTag = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (addDisabled) return;

    setIsMutating(true);

    try {
      const createdTag = onCreateTag
        ? await onCreateTag({ name: normalizedCreateName, color: createColor })
        : {
          id: nextTagId(tags),
          name: normalizedCreateName,
          color: createColor,
          usage: 0,
        };

      commitTags((current) => [createdTag, ...current]);
      setCreateName("");
      setCreateColor(TAG_COLORS[0].value);
      setToast("标签已添加");
      inputRef.current?.focus();
    } catch {
      setToast("标签添加失败，请稍后重试");
    } finally {
      setIsMutating(false);
    }
  };

  const startEdit = (tag: CustomProductTag) => {
    setEditingId(tag.id);
    setEditName(tag.name);
    setEditColor(tag.color);
  };

  const cancelEdit = () => {
    setEditingId(null);
  };

  const saveEdit = async () => {
    if (editingId == null || saveDisabled) return;

    setIsMutating(true);

    try {
      const updatedTag = onUpdateTag
        ? await onUpdateTag(String(editingId), { name: normalizedEditName, color: editColor })
        : null;

      commitTags((current) => current.map((tag) => (
        tag.id === editingId
          ? updatedTag ?? { ...tag, name: normalizedEditName, color: editColor }
          : tag
      )));

      setEditingId(null);
      setToast("标签已保存");
    } catch {
      setToast("标签保存失败，请稍后重试");
    } finally {
      setIsMutating(false);
    }
  };

  const handleEditKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void saveEdit();
    }
    if (event.key === "Escape") {
      event.preventDefault();
      cancelEdit();
    }
  };

  const confirmDelete = async () => {
    if (deleteId == null) return;

    const tagName = deleteTag?.name ?? "标签";
    setIsMutating(true);

    try {
      if (onDeleteTag) await onDeleteTag(String(deleteId));

      commitTags((current) => current.filter((tag) => tag.id !== deleteId));

      if (editingId === deleteId) setEditingId(null);
      setDeleteId(null);
      setToast(`已删除「${tagName}」`);
    } catch {
      setToast("标签删除失败，请稍后重试");
    } finally {
      setIsMutating(false);
    }
  };

  if (!open) return null;

  return (
    <div className="custom-tag-manager" aria-hidden={!open}>
      <button
        type="button"
        className="custom-tag-manager__mask"
        aria-label="关闭自定义标签管理"
        onClick={closeModal}
      />

      <section
        className="custom-tag-manager__modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="customTagManagerTitle"
      >
        <header className="custom-tag-manager__head">
          <div>
            <div className="custom-tag-manager__title" id="customTagManagerTitle">
              自定义标签管理
            </div>
            <div className="custom-tag-manager__sub">
              创建和维护产品自定义标签
            </div>
          </div>
          <button
            className="custom-tag-manager__close"
            type="button"
            aria-label="关闭"
            onClick={closeModal}
          >
            ×
          </button>
        </header>

        <div className="custom-tag-manager__body">
          <section className="custom-tag-manager__create-box">
            <div className="custom-tag-manager__create-head">
              <div className="custom-tag-manager__create-title">添加标签</div>
              <div className="custom-tag-manager__preview-wrap">
                <span>预览</span>
                <span className="custom-tag-manager__tag-preview">
                  <i
                    className="custom-tag-manager__preview-dot"
                    style={{ background: createColor }}
                  />
                  <span>{normalizedCreateName || "新标签"}</span>
                </span>
              </div>
            </div>

            <form onSubmit={(event) => { void addTag(event); }}>
              <div className="custom-tag-manager__form-row">
                <div className="custom-tag-manager__input-wrap">
                  <label
                    className="custom-tag-manager__label"
                    htmlFor="customTagManagerName"
                  >
                    标签名称
                  </label>
                  <input
                    ref={inputRef}
                    className={createError
                      ? "custom-tag-manager__name-input custom-tag-manager__name-input--error"
                      : "custom-tag-manager__name-input"}
                    id="customTagManagerName"
                    maxLength={MAX_TAG_NAME_LENGTH}
                    autoComplete="off"
                    placeholder="输入标签名称，最多16个字符"
                    value={createName}
                    onChange={(event) => setCreateName(event.target.value)}
                  />
                  <div className={createError
                    ? "custom-tag-manager__helper custom-tag-manager__helper--error"
                    : "custom-tag-manager__helper"}
                  >
                    {createError || "必填 · 不允许重名 · Enter 可快速添加"}
                  </div>
                </div>

                <button
                  className="custom-tag-manager__primary custom-tag-manager__add-btn"
                  type="submit"
                  disabled={addDisabled}
                >
                  添加
                </button>
              </div>

              <div className="custom-tag-manager__color-area">
                <span className="custom-tag-manager__label">标签颜色</span>
                <ColorOptions selectedColor={createColor} onSelect={setCreateColor} />
              </div>
            </form>
          </section>

          <div className="custom-tag-manager__list-head">
            <div className="custom-tag-manager__list-title">已有标签</div>
            <div className="custom-tag-manager__list-count">{tags.length} 个</div>
          </div>

          <div className="custom-tag-manager__tag-list">
            {tags.length === 0 ? (
              <div className="custom-tag-manager__empty">还没有自定义标签</div>
            ) : tags.map((tag) => (
              editingId === tag.id ? (
                <div
                  key={tag.id}
                  className="custom-tag-manager__tag-row custom-tag-manager__tag-row--editing"
                >
                  <div className="custom-tag-manager__inline-edit">
                    <div className="custom-tag-manager__inline-edit-top">
                      <input
                        className={editError
                          ? "custom-tag-manager__name-input custom-tag-manager__name-input--error"
                          : "custom-tag-manager__name-input"}
                        maxLength={MAX_TAG_NAME_LENGTH}
                        value={editName}
                        aria-label="编辑标签名称"
                        onChange={(event) => setEditName(event.target.value)}
                        onKeyDown={handleEditKeyDown}
                      />
                      <span className="custom-tag-manager__inline-usage">
                        {editingTag?.usage ?? tag.usage} 个产品
                      </span>
                      <div className="custom-tag-manager__inline-actions">
                        <button
                          type="button"
                          className="custom-tag-manager__mini custom-tag-manager__mini--cancel"
                          onClick={cancelEdit}
                        >
                          取消
                        </button>
                        <button
                          type="button"
                          className="custom-tag-manager__mini custom-tag-manager__mini--save"
                          disabled={saveDisabled}
                          onClick={() => { void saveEdit(); }}
                        >
                          保存
                        </button>
                      </div>
                    </div>

                    <div className="custom-tag-manager__inline-edit-bottom">
                      <ColorOptions
                        compact
                        selectedColor={editColor}
                        onSelect={setEditColor}
                      />
                      <div className={editError
                        ? "custom-tag-manager__inline-helper custom-tag-manager__inline-helper--error"
                        : "custom-tag-manager__inline-helper"}
                      >
                        {editError}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div key={tag.id} className="custom-tag-manager__tag-row">
                  <div className="custom-tag-manager__tag-main">
                    <span
                      className="custom-tag-manager__tag-dot"
                      style={{ background: tag.color }}
                    />
                    <span className="custom-tag-manager__tag-name">{tag.name}</span>
                  </div>
                  <div className="custom-tag-manager__usage">{tag.usage} 个产品</div>
                  <div className="custom-tag-manager__actions">
                    <button
                      type="button"
                      className="custom-tag-manager__text-btn"
                      disabled={busy}
                      onClick={() => startEdit(tag)}
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      className="custom-tag-manager__text-btn custom-tag-manager__text-btn--danger"
                      disabled={busy}
                      onClick={() => setDeleteId(tag.id)}
                    >
                      删除
                    </button>
                  </div>
                </div>
              )
            ))}
          </div>
        </div>

        {deleteTag ? (
          <div className="custom-tag-manager__confirm-layer" aria-hidden="false">
            <div
              className="custom-tag-manager__confirm"
              role="alertdialog"
              aria-modal="true"
              aria-labelledby="customTagDeleteTitle"
            >
              <div className="custom-tag-manager__confirm-title" id="customTagDeleteTitle">
                删除标签
              </div>
              <div className="custom-tag-manager__confirm-text">
                {deleteTag.usage > 0 ? (
                  <>
                    「<strong>{deleteTag.name}</strong>」当前已应用于{" "}
                    <strong>{deleteTag.usage}</strong> 个产品。
                    <br />
                    删除后，这些产品将同时移除该标签。
                  </>
                ) : (
                  <>
                    确定删除「<strong>{deleteTag.name}</strong>」？该标签当前未被产品使用。
                  </>
                )}
              </div>
              <div className="custom-tag-manager__confirm-actions">
                <button
                  type="button"
                  className="custom-tag-manager__ghost"
                  onClick={() => setDeleteId(null)}
                >
                  取消
                </button>
                <button
                  type="button"
                  className="custom-tag-manager__danger"
                  onClick={() => { void confirmDelete(); }}
                >
                  删除
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </section>

      {toast ? (
        <div className="custom-tag-manager__toast" role="status" aria-live="polite">
          {toast}
        </div>
      ) : null}
    </div>
  );
}

export default CustomTagManagerModal;
