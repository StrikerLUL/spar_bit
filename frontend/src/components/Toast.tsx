import * as React from "react";
import { cn } from "@/lib/utils";

type ToastKind = "success" | "error" | "info";
interface Toast { id: number; kind: ToastKind; title: string; detail?: string }

const ToastContext = React.createContext<{
  push: (kind: ToastKind, title: string, detail?: string) => void;
}>({ push: () => {} });

export const useToast = () => React.useContext(ToastContext);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);
  const nextId = React.useRef(1);

  const push = React.useCallback((kind: ToastKind, title: string, detail?: string) => {
    const id = nextId.current++;
    setToasts((current) => [...current, { id, kind, title, detail }]);
    // Fehler bleiben laenger stehen - man will sie lesen koennen.
    window.setTimeout(() => {
      setToasts((current) => current.filter((t) => t.id !== id));
    }, kind === "error" ? 8000 : 4000);
  }, []);

  const dismiss = (id: number) =>
    setToasts((current) => current.filter((t) => t.id !== id));

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div
        className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 p-4 sm:inset-x-auto sm:right-0 sm:items-end"
        role="status"
        aria-live="polite"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            onClick={() => dismiss(toast.id)}
            className={cn(
              "pointer-events-auto w-full max-w-sm cursor-pointer rounded-lg border p-3.5",
              "shadow-lg shadow-black/30 animate-slide-up",
              toast.kind === "success" && "border-success/30 bg-success/10",
              toast.kind === "error" && "border-destructive/30 bg-destructive/10",
              toast.kind === "info" && "border-border bg-card/95",
            )}
          >
            <p className="text-sm font-medium">{toast.title}</p>
            {toast.detail && (
              <p className="mt-1 break-words text-xs text-muted-foreground">{toast.detail}</p>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
