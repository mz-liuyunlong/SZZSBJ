import { useEffect, type RefObject } from "react";
import {
  readPageStateCache,
  writePageStateCache,
} from "@/shared/page-state/pageStateCache";

interface ScrollPosition {
  scrollTop: number;
  scrollLeft: number;
}

function resolveScrollTarget(
  root: HTMLElement | null,
  targetSelector?: string,
): HTMLElement | null {
  if (!root) return null;
  if (!targetSelector) return root;
  return root.querySelector<HTMLElement>(targetSelector);
}

export function useElementScrollRestoration(
  cacheKey: string,
  rootRef: RefObject<HTMLElement | null>,
  targetSelector?: string,
) {
  useEffect(() => {
    const rootElement = rootRef.current;
    let disposed = false;
    let animationFrame = 0;
    let cleanupScrollListener: (() => void) | undefined;
    let observedTarget: HTMLElement | null = null;
    let restoreAttempts = 0;

    const saveScrollPosition = (target: HTMLElement) => {
      writePageStateCache<ScrollPosition>(cacheKey, {
        scrollTop: target.scrollTop,
        scrollLeft: target.scrollLeft,
      });
    };

    const attachAndRestore = () => {
      if (disposed) return;

      const target = resolveScrollTarget(rootElement, targetSelector);

      if (target) {
        if (observedTarget !== target) {
          cleanupScrollListener?.();
          observedTarget = target;

          const handleScroll = () => saveScrollPosition(target);
          target.addEventListener("scroll", handleScroll, { passive: true });
          cleanupScrollListener = () => target.removeEventListener("scroll", handleScroll);
        }

        const savedPosition = readPageStateCache<ScrollPosition>(cacheKey);
        if (savedPosition && restoreAttempts < 20) {
          const maxTop = Math.max(target.scrollHeight - target.clientHeight, 0);
          const maxLeft = Math.max(target.scrollWidth - target.clientWidth, 0);

          target.scrollTop = Math.min(savedPosition.scrollTop, maxTop);
          target.scrollLeft = Math.min(savedPosition.scrollLeft, maxLeft);
        }
      }

      restoreAttempts += 1;
      if (restoreAttempts < 30) {
        animationFrame = window.requestAnimationFrame(attachAndRestore);
      }
    };

    animationFrame = window.requestAnimationFrame(attachAndRestore);

    return () => {
      disposed = true;
      window.cancelAnimationFrame(animationFrame);

      if (observedTarget) saveScrollPosition(observedTarget);
      cleanupScrollListener?.();
    };
  }, [cacheKey, rootRef, targetSelector]);
}
