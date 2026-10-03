import { MapPin } from "lucide-react";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/hooks/useAuth";
import { useLocationFilter } from "@/hooks/useLocationFilter";
import { useLocations } from "@/hooks/useOrganization";
import { Permission } from "@/lib/permissions";

const ALL = "all";

/** FR-36: pick one office location or all; used by dashboard, cameras and live view. */
export function LocationSwitcher() {
  const { can } = useAuth();
  const allowed = can(Permission.organizationView);
  const { locationId, setLocationId } = useLocationFilter();
  const locations = useLocations(allowed);
  if (!allowed || (locations.data?.data.length ?? 0) < 2) return null;
  return (
    <Select value={locationId ? String(locationId) : ALL} onValueChange={(v) => setLocationId(v === ALL ? null : Number(v))}>
      <SelectTrigger size="sm" aria-label="Office location" className="w-44">
        <MapPin aria-hidden />
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>All locations</SelectItem>
        {locations.data?.data.map((location) => (
          <SelectItem key={location.id} value={String(location.id)}>
            {location.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
