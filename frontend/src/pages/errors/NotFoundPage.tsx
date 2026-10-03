import { SearchX } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <EmptyState
      icon={SearchX}
      title="Page not found"
      description="The link may be old, or the record was deleted."
      action={
        <Button asChild variant="outline">
          <Link to="/">Go to my start page</Link>
        </Button>
      }
    />
  );
}
