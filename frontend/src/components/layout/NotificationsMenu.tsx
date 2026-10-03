import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { Link } from "react-router-dom";

import { listCorrections, listUnknownFaces } from "@/api/generated/endpoints";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/hooks/useAuth";
import { Permission } from "@/lib/permissions";

/** Work waiting for the user: pending corrections and unknown faces to review. */
export function NotificationsMenu() {
  const { can } = useAuth();
  const canCorrect = can(Permission.attendanceCorrect);
  const canReview = can(Permission.unknownFacesReview);
  const corrections = useQuery({
    queryKey: ["corrections", { status: "pending", page_size: 1 }],
    queryFn: () => listCorrections({ status: "pending", page: 1, page_size: 1 }),
    enabled: canCorrect,
    refetchInterval: 120_000,
  });
  const unknown = useQuery({
    queryKey: ["unknown-faces", { review_status: "pending", page_size: 1 }],
    queryFn: () => listUnknownFaces({ review_status: "pending", page: 1, page_size: 1 }),
    enabled: canReview,
    refetchInterval: 120_000,
  });
  if (!canCorrect && !canReview) return null;
  const pendingCorrections = corrections.data?.pagination.total ?? 0;
  const pendingUnknown = unknown.data?.pagination.total ?? 0;
  const total = pendingCorrections + pendingUnknown;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={`Notifications: ${total} waiting`}>
          <Bell />
          {total > 0 && (
            <span className="bg-status-bad absolute -top-0.5 -right-0.5 min-w-4 rounded-full px-1 text-[10px] leading-4 font-semibold text-white">
              {total > 99 ? "99+" : total}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel>Waiting for you</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {canCorrect && (
          <DropdownMenuItem asChild>
            <Link to="/corrections?status=pending">{pendingCorrections} correction requests to review</Link>
          </DropdownMenuItem>
        )}
        {canReview && (
          <DropdownMenuItem asChild>
            <Link to="/unknown-faces">{pendingUnknown} unknown faces to review</Link>
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
