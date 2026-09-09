/** Renders an accessible native resize handle without coupling column width to storage. */
import { useRef, type KeyboardEvent, type PointerEvent } from "react";
import "@/components/report-table/reportTable.css";

interface ResizableColumnTitleProps {
  label: string;
  minWidth: number;
  width: number;
  onWidthChange: (width: number) => void;
}

function ResizableColumnTitle({
  label,
  minWidth,
  width,
  onWidthChange,
}: ResizableColumnTitleProps) {
  const session = useRef<{
    pointerId: number;
    startWidth: number;
    startX: number;
    width: number;
  } | undefined>(undefined);
  const guideRef = useRef<HTMLSpanElement>(null);

  const hideGuide = () => {
    const guide = guideRef.current;
    if (!guide) return;
    guide.style.visibility = "hidden";
    guide.style.transform = "translateX(0)";
  };

  const startResize = (event: PointerEvent<HTMLSpanElement>) => {
    event.preventDefault();
    event.stopPropagation();
    const shell = event.currentTarget.closest<HTMLElement>(".report-table-shell");
    const handleRect = event.currentTarget.getBoundingClientRect();
    const shellRect = shell?.getBoundingClientRect();
    session.current = {
      pointerId: event.pointerId,
      startWidth: width,
      startX: event.clientX,
      width,
    };
    const guide = guideRef.current;
    if (guide) {
      guide.style.insetBlockStart = `${shellRect?.top ?? handleRect.top}px`;
      guide.style.insetInlineStart = `${handleRect.right}px`;
      guide.style.height = `${shellRect?.height ?? handleRect.height}px`;
      guide.style.visibility = "visible";
    }
    event.currentTarget.dataset.resizing = "true";
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const resize = (event: PointerEvent<HTMLSpanElement>) => {
    if (!session.current) return;
    event.stopPropagation();
    const nextWidth = Math.max(
      minWidth,
      session.current.startWidth + event.clientX - session.current.startX,
    );
    session.current.width = nextWidth;
    if (guideRef.current) {
      guideRef.current.style.transform = `translateX(${nextWidth - session.current.startWidth}px)`;
    }
  };

  const finishResize = (event: PointerEvent<HTMLSpanElement>, apply: boolean) => {
    event.stopPropagation();
    const activeSession = session.current;
    if (activeSession?.pointerId === event.pointerId) {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    }
    session.current = undefined;
    delete event.currentTarget.dataset.resizing;
    hideGuide();
    if (apply && activeSession && activeSession.width !== activeSession.startWidth) {
      onWidthChange(activeSession.width);
    }
  };

  const resizeWithKeyboard = (event: KeyboardEvent<HTMLSpanElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    event.stopPropagation();
    onWidthChange(Math.max(minWidth, width + (event.key === "ArrowLeft" ? -8 : 8)));
  };

  return (
    <span className="report-table-resizable-title">
      <span>{label}</span>
      <span
        className="report-table-resize-handle"
        role="separator"
        tabIndex={0}
        aria-label={`调整列宽：${label}`}
        aria-orientation="vertical"
        aria-valuemin={minWidth}
        aria-valuenow={width}
        onPointerDown={startResize}
        onPointerMove={resize}
        onPointerUp={(event) => finishResize(event, true)}
        onPointerCancel={(event) => finishResize(event, false)}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
        }}
        onKeyDown={resizeWithKeyboard}
      >
        <span ref={guideRef} className="report-table-resize-guide" aria-hidden="true" />
      </span>
    </span>
  );
}

export default ResizableColumnTitle;
