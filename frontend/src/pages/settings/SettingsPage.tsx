import type { SettingItem } from "@/api/generated/model";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { HolidaysTab } from "@/components/settings/HolidaysTab";
import { ApiKeysCard, IntegrationActionsCard } from "@/components/settings/IntegrationCard";
import { OrganizationTab } from "@/components/settings/OrganizationTab";
import { SettingsGroupForm } from "@/components/settings/SettingsGroupForm";
import { ShiftsTab } from "@/components/settings/ShiftsTab";
import { UsersTab } from "@/components/settings/UsersTab";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/hooks/useAuth";
import { useSettings } from "@/hooks/useSettings";
import { useUrlState } from "@/hooks/useUrlState";
import { Permission } from "@/lib/permissions";

const TABS = [
  { value: "general", label: "General" },
  { value: "organization", label: "Organization" },
  { value: "shifts", label: "Shifts" },
  { value: "holidays", label: "Holidays" },
  { value: "recognition", label: "Recognition" },
  { value: "retention", label: "Retention" },
  { value: "notifications", label: "Notifications" },
  { value: "integration", label: "Integration" },
  { value: "users", label: "Users and roles" },
] as const;

function byGroups(items: SettingItem[], groups: string[]): SettingItem[] {
  return items.filter((item) => groups.includes(item.group));
}

function GroupCard({ items, groups, title }: { items: SettingItem[] | undefined; groups: string[]; title?: string }) {
  if (!items) return <Skeleton className="h-64" />;
  return (
    <Card>
      <CardContent className="pt-6">
        <SettingsGroupForm key={groups.join()} items={byGroups(items, groups)} title={title} />
      </CardContent>
    </Card>
  );
}

/** §13 screen 13 (Admin). */
export function SettingsPage() {
  const { can } = useAuth();
  const url = useUrlState();
  const canSettings = can(Permission.settingsManage);
  const canUsers = can(Permission.usersManage);
  const settings = useSettings(canSettings);
  const tabs = TABS.filter((tab) => (tab.value === "users" ? canUsers : canSettings));
  const tab = tabs.some((t) => t.value === url.get("tab")) ? (url.get("tab") as string) : tabs[0]?.value;
  const items = settings.data?.data;

  return (
    <>
      <PageHeader title="Settings" description="Working rules, recognition, retention, notifications and access." />
      {settings.isError ? (
        <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />
      ) : (
        <Tabs value={tab} onValueChange={(value) => url.set({ tab: value })}>
          <TabsList className="h-auto flex-wrap">
            {tabs.map((t) => (
              <TabsTrigger key={t.value} value={t.value}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="general">
            <GroupCard items={items} groups={["general", "attendance"]} />
          </TabsContent>
          <TabsContent value="organization">
            <OrganizationTab />
          </TabsContent>
          <TabsContent value="shifts">
            <ShiftsTab />
          </TabsContent>
          <TabsContent value="holidays">
            <HolidaysTab />
          </TabsContent>
          <TabsContent value="recognition" className="space-y-4">
            <GroupCard items={items} groups={["recognition"]} title="Recognition and enrollment" />
            <GroupCard items={items} groups={["engine"]} title="Engine scheduling (CPU)" />
          </TabsContent>
          <TabsContent value="retention">
            <GroupCard items={items} groups={["retention"]} />
          </TabsContent>
          <TabsContent value="notifications">
            <GroupCard items={items} groups={["notifications"]} />
          </TabsContent>
          <TabsContent value="integration" className="space-y-4">
            <GroupCard items={items} groups={["integration"]} />
            <ApiKeysCard />
            <IntegrationActionsCard />
          </TabsContent>
          <TabsContent value="users" className="space-y-4">
            {canSettings && <GroupCard items={items} groups={["auth"]} title="Sign-in" />}
            <UsersTab />
          </TabsContent>
        </Tabs>
      )}
    </>
  );
}
