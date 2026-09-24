"use client";

import { useEffect, useMemo, useSyncExternalStore } from "react";
import { apiFetch } from "@/lib/api";
import { createAutosaveQueue } from "@/lib/autosave-queue";

type PickCard = { matchup_id: string; selected_roster_id: number }[];

export function usePredictionAutosave(weekId?: string) {
  const queue = useMemo(() => createAutosaveQueue<PickCard>(picks => {
    if (!weekId) return Promise.reject(new Error("No prediction week loaded."));
    return apiFetch(`/predictions/weeks/${weekId}/picks`, {
      method: "PUT", body: JSON.stringify({ picks }), keepalive: true,
    });
  }), [weekId]);
  const state = useSyncExternalStore(queue.subscribe, queue.getSnapshot, queue.getSnapshot);

  useEffect(() => {
    const leaveMessage = "Your latest picks have not been saved. Leave this page anyway?";
    function beforeUnload(event: BeforeUnloadEvent) {
      if (!queue.hasUnsavedChanges()) return;
      event.preventDefault();
      event.returnValue = "";
    }
    function beforeNavigate(event: MouseEvent) {
      if (!queue.hasUnsavedChanges() || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!(link instanceof HTMLAnchorElement) || link.target === "_blank" || link.hasAttribute("download")) return;
      const destination = new URL(link.href);
      if (destination.origin === location.origin && destination.pathname === location.pathname && destination.search === location.search) return;
      if (!window.confirm(leaveMessage)) {
        event.preventDefault();
        event.stopPropagation();
      }
    }
    // The Navigation API also covers same-document Back/Forward navigation,
    // which does not fire beforeunload in browsers that support it.
    const navigation = (window as Window & { navigation?: EventTarget }).navigation;
    function beforeTraverse(event: Event) {
      const navigationEvent = event as Event & { navigationType?: string; hashChange?: boolean };
      if (navigationEvent.navigationType === "traverse" && !navigationEvent.hashChange && event.cancelable && queue.hasUnsavedChanges() && !window.confirm(leaveMessage)) {
        event.preventDefault();
      }
    }
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", beforeNavigate, true);
    navigation?.addEventListener("navigate", beforeTraverse);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      document.removeEventListener("click", beforeNavigate, true);
      navigation?.removeEventListener("navigate", beforeTraverse);
    };
  }, [queue]);

  return { ...state, submit: queue.submit, retry: queue.retry };
}
