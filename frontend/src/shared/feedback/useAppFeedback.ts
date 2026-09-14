import { useContext } from "react";
import { AppFeedbackContext } from "@/shared/feedback/AppFeedbackContext";

export function useAppFeedback() {
  const context = useContext(AppFeedbackContext);

  if (!context) {
    throw new Error("useAppFeedback must be used inside AppFeedbackProvider");
  }

  return context;
}

export default useAppFeedback;
