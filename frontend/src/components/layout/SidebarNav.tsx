import { NavLink } from "react-router-dom";

import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";
import { visibleNavItems } from "@/routes/navigation";

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const { can, user } = useAuth();
  const items = visibleNavItems(can, user?.role === "employee");
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5">
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "relative flex items-center gap-3 rounded-md border px-3 py-2 text-sm transition-colors",
              isActive
                ? "bg-sidebar-accent text-sidebar-accent-foreground border-sidebar-border before:bg-sidebar-primary font-semibold shadow-xs before:absolute before:inset-y-2 before:left-0 before:w-1 before:rounded-r-full"
                : "text-sidebar-foreground hover:bg-sidebar-accent/70 border-transparent font-medium",
            )
          }
        >
          <Icon className="size-[1.125rem] shrink-0" aria-hidden />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
