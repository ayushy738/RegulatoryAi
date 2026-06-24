import { Loader2 } from "lucide-react";

export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="state-block">
      <Loader2 className="spin" size={22} />
      <p>{label}</p>
    </div>
  );
}
