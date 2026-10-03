import { ShieldOff } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";

export function ForbiddenPage() {
  return (
    <EmptyState
      icon={ShieldOff}
      title="You do not have access to this page"
      description="Your role does not include this screen. Ask a Super Admin if you need access."
      action={
        <Button asChild variant="outline">
          <Link to="/">Go to my start page</Link>
        </Button>
      }
    />
  );
}
