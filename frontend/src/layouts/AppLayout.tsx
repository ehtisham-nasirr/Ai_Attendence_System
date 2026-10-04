import { Menu } from "lucide-react";
import { useState } from "react";
import { Outlet } from "react-router-dom";

import { LiveFeedProvider } from "@/components/common/LiveFeedProvider";
import { LocationFilterProvider } from "@/components/common/LocationFilterProvider";
import { Brand } from "@/components/layout/Brand";
import { LiveIndicator } from "@/components/layout/LiveIndicator";
import { LocationSwitcher } from "@/components/layout/LocationSwitcher";
import { NotificationsMenu } from "@/components/layout/NotificationsMenu";
import { SidebarNav } from "@/components/layout/SidebarNav";
import { UserMenu } from "@/components/layout/UserMenu";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";

/** Left sidebar + top bar (§13). Below `lg` the sidebar becomes a drawer, so tablets work. */
export function AppLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  return (
    <LocationFilterProvider>
      <LiveFeedProvider>
        <div className="bg-background flex min-h-screen">
          <aside className="bg-sidebar text-sidebar-foreground border-sidebar-border sticky top-0 hidden h-screen w-60 shrink-0 flex-col gap-6 border-r p-3 lg:flex">
            <Brand />
            <SidebarNav />
          </aside>
          <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
            <SheetContent side="left" className="bg-sidebar text-sidebar-foreground w-64 p-3">
              <SheetHeader className="p-0">
                <SheetTitle asChild>
                  <div>
                    <Brand />
                  </div>
                </SheetTitle>
              </SheetHeader>
              <SidebarNav onNavigate={() => setDrawerOpen(false)} />
            </SheetContent>
          </Sheet>
          <div className="flex min-w-0 flex-1 flex-col">
            <header className="bg-card sticky top-0 z-30 flex h-14 items-center gap-2 border-b px-4 md:px-6">
              <Button
                variant="ghost"
                size="icon"
                className="lg:hidden"
                aria-label="Open navigation"
                onClick={() => setDrawerOpen(true)}
              >
                <Menu />
              </Button>
              <LocationSwitcher />
              <div className="ml-auto flex items-center gap-2">
                <LiveIndicator />
                <NotificationsMenu />
                <UserMenu />
              </div>
            </header>
            <main className="mx-auto w-full max-w-[1600px] flex-1 p-4 md:p-6">
              <Outlet />
            </main>
          </div>
        </div>
      </LiveFeedProvider>
    </LocationFilterProvider>
  );
}
