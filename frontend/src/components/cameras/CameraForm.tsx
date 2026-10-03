import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";

import type { CameraCreate, CameraOut, CameraRole, CameraTestOut, CameraUpdate } from "@/api/generated/model";
import { CameraTestPanel } from "@/components/cameras/CameraTestPanel";
import { OperatingHoursEditor } from "@/components/cameras/OperatingHoursEditor";
import { RoiEditor, type Point } from "@/components/cameras/RoiEditor";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { useCameraMutations } from "@/hooks/useCameras";
import { useLocations } from "@/hooks/useOrganization";
import { showError, showFormError } from "@/lib/forms";
import { cameraRoleLabel } from "@/lib/labels";
import { cameraSchema, type CameraFormValues, type OperatingWindow } from "@/lib/schemas/camera";

const ENTRANCE_ROLES = new Set<CameraRole>(["ENTRY", "EXIT", "ENTRY_EXIT"]);

function toValues(camera: CameraOut | undefined): CameraFormValues {
  const hours = (camera?.operating_hours ?? null) as OperatingWindow[] | null;
  return {
    name: camera?.name ?? "",
    location_id: camera ? String(camera.location_id) : "",
    role: camera?.role ?? "ENTRY",
    rtsp_url: "",
    substream_url: "",
    clear_substream: false,
    engine_node: camera?.engine_node ?? "node-1",
    priority: camera?.priority ?? 0,
    always_on: !hours || hours.length === 0,
    operating_hours: hours ?? [],
    roi_polygon: ((camera?.roi_polygon ?? []) as number[][]).map(([x, y]) => [x, y] as Point),
    use_default_fps: camera?.fps === null || camera?.fps === undefined,
    fps: camera?.fps ?? 4,
    use_default_threshold: camera?.match_threshold === null || camera?.match_threshold === undefined,
    match_threshold: camera?.match_threshold ?? 0.45,
    liveness_enabled: camera?.liveness_enabled ?? false,
    is_enabled: camera?.is_enabled ?? true,
  };
}

function toCreate(values: CameraFormValues): CameraCreate {
  return {
    name: values.name.trim(),
    location_id: Number(values.location_id),
    role: values.role,
    rtsp_url: values.rtsp_url.trim(),
    substream_url: values.substream_url.trim() || null,
    engine_node: values.engine_node.trim(),
    priority: values.priority,
    operating_hours: values.always_on ? null : values.operating_hours,
    roi_polygon: values.roi_polygon.length >= 3 ? values.roi_polygon : null,
    fps: values.use_default_fps ? null : values.fps,
    match_threshold: values.use_default_threshold ? null : values.match_threshold,
    liveness_enabled: values.liveness_enabled,
    is_enabled: values.is_enabled,
  };
}

function toUpdate(values: CameraFormValues): CameraUpdate {
  const { rtsp_url, substream_url, ...rest } = toCreate(values);
  return {
    ...rest,
    ...(rtsp_url ? { rtsp_url } : {}),
    ...(substream_url ? { substream_url } : {}),
    clear_substream: values.clear_substream,
    clear_roi: values.roi_polygon.length < 3,
  };
}

/**
 * Add/edit drawer content (§13 screen 6, FR-1..FR-6). Stream URLs are write-only: the API stores them
 * encrypted and never returns them, so editing leaves them blank unless they change.
 */
export function CameraForm({ camera, onSaved }: { camera?: CameraOut; onSaved: (camera: CameraOut) => void }) {
  const locations = useLocations();
  const { create, update, test } = useCameraMutations();
  const [saved, setSaved] = useState<CameraOut | undefined>(camera);
  const [testResult, setTestResult] = useState<CameraTestOut | null>(null);
  const form = useForm<CameraFormValues>({
    resolver: zodResolver(cameraSchema(!camera)),
    defaultValues: toValues(camera),
  });
  const [role, alwaysOn, defaultFps, defaultThreshold] = useWatch({
    control: form.control,
    name: ["role", "always_on", "use_default_fps", "use_default_threshold"],
  });
  const snapshot = testResult?.ok && testResult.snapshot_jpeg_b64 ? `data:image/jpeg;base64,${testResult.snapshot_jpeg_b64}` : null;

  const runTest = async (cameraId: number) => {
    try {
      setTestResult((await test.mutateAsync({ id: cameraId, useSubstream: false })).data);
    } catch (error) {
      showError(error);
    }
  };

  const submit = form.handleSubmit(async (values) => {
    try {
      const result = saved
        ? await update.mutateAsync({ id: saved.id, body: toUpdate(values) })
        : await create.mutateAsync(toCreate(values));
      setSaved(result.data);
      form.reset({ ...values, rtsp_url: "", substream_url: "", clear_substream: false });
      onSaved(result.data);
      if (!saved) await runTest(result.data.id); // FR-2: test on save
    } catch (error) {
      showFormError(form, error);
    }
  });

  const pending = create.isPending || update.isPending;
  return (
    <Form {...form}>
      <form onSubmit={submit} className="space-y-5" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Name</FormLabel>
                <FormControl>
                  <Input placeholder="Main entrance" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="location_id"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Location</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Choose a location" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {(locations.data?.data ?? []).map((location) => (
                      <SelectItem key={location.id} value={String(location.id)}>
                        {location.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="role"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Role</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {(Object.keys(cameraRoleLabel) as CameraRole[]).map((value) => (
                      <SelectItem key={value} value={value}>
                        {cameraRoleLabel[value]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription>Entry cameras record check-in, exit cameras check-out.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="engine_node"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Engine node</FormLabel>
                <FormControl>
                  <Input {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="rtsp_url"
            render={({ field }) => (
              <FormItem className="sm:col-span-2">
                <FormLabel>Main stream URL</FormLabel>
                <FormControl>
                  <Input
                    type="password"
                    autoComplete="off"
                    placeholder={saved ? `Stored (${saved.stream_host}). Leave blank to keep.` : "rtsp://user:password@10.0.0.5:554/Streaming/101"}
                    {...field}
                  />
                </FormControl>
                <FormDescription>Stored encrypted and never shown again.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="substream_url"
            render={({ field }) => (
              <FormItem className="sm:col-span-2">
                <FormLabel>Sub-stream URL (optional)</FormLabel>
                <FormControl>
                  <Input
                    type="password"
                    autoComplete="off"
                    placeholder={saved?.has_substream ? "Stored. Leave blank to keep." : "Lower resolution stream for idle detection"}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          {saved?.has_substream && (
            <FormField
              control={form.control}
              name="clear_substream"
              render={({ field }) => (
                <FormItem className="flex items-center gap-2 sm:col-span-2">
                  <FormControl>
                    <Checkbox checked={field.value} onCheckedChange={(checked) => field.onChange(checked === true)} />
                  </FormControl>
                  <FormLabel className="font-normal">Remove the stored sub-stream</FormLabel>
                </FormItem>
              )}
            />
          )}
        </div>

        <CameraTestPanel
          result={testResult}
          pending={test.isPending}
          disabled={!saved}
          onTest={() => saved && void runTest(saved.id)}
        />

        <Separator />
        <div className="space-y-2">
          <h3 className="font-medium">Region of interest</h3>
          <FormField
            control={form.control}
            name="roi_polygon"
            render={({ field }) => <RoiEditor snapshot={snapshot} value={field.value as Point[]} onChange={field.onChange} />}
          />
        </div>

        <Separator />
        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-3">
            <FormField
              control={form.control}
              name="use_default_fps"
              render={({ field }) => (
                <FormItem className="flex items-center justify-between gap-2">
                  <FormLabel>Processing FPS: use default for the role</FormLabel>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
            {!defaultFps && (
              <FormField
                control={form.control}
                name="fps"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Detection rate when active: {field.value} fps</FormLabel>
                    <FormControl>
                      <Slider min={0.5} max={15} step={0.5} value={[field.value]} onValueChange={([v]) => field.onChange(v)} />
                    </FormControl>
                    <FormDescription>Higher rates use more CPU on the engine node.</FormDescription>
                  </FormItem>
                )}
              />
            )}
          </div>
          <div className="space-y-3">
            <FormField
              control={form.control}
              name="use_default_threshold"
              render={({ field }) => (
                <FormItem className="flex items-center justify-between gap-2">
                  <FormLabel>Match threshold: use global setting</FormLabel>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
            {!defaultThreshold && (
              <FormField
                control={form.control}
                name="match_threshold"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Match threshold: {field.value.toFixed(2)}</FormLabel>
                    <FormControl>
                      <Slider min={0.2} max={0.8} step={0.01} value={[field.value]} onValueChange={([v]) => field.onChange(v)} />
                    </FormControl>
                    <FormDescription>
                      Lower values accept weaker matches and raise false recognitions. Change only after evaluating
                      this camera.
                    </FormDescription>
                  </FormItem>
                )}
              />
            )}
          </div>
          <FormField
            control={form.control}
            name="priority"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Priority (0–100)</FormLabel>
                <FormControl>
                  <Input type="number" min={0} max={100} value={field.value} onChange={(e) => field.onChange(Number(e.target.value))} />
                </FormControl>
                <FormDescription>Higher-priority cameras keep their rate longest under load.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
          <div className="space-y-3">
            <FormField
              control={form.control}
              name="liveness_enabled"
              render={({ field }) => (
                <FormItem className="flex items-center justify-between gap-2">
                  <div>
                    <FormLabel>Anti-spoofing (liveness)</FormLabel>
                    <FormDescription>
                      {ENTRANCE_ROLES.has(role) ? "Recommended for entrance cameras." : "Usually only on entrances."}
                    </FormDescription>
                  </div>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="is_enabled"
              render={({ field }) => (
                <FormItem className="flex items-center justify-between gap-2">
                  <FormLabel>Camera enabled</FormLabel>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
          </div>
        </div>

        <Separator />
        <div className="space-y-2">
          <FormField
            control={form.control}
            name="always_on"
            render={({ field }) => (
              <FormItem className="flex items-center justify-between gap-2">
                <div>
                  <FormLabel>Operating hours: always on</FormLabel>
                  <FormDescription>Outside its hours a camera is paused and uses no CPU.</FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />
          {!alwaysOn && (
            <FormField
              control={form.control}
              name="operating_hours"
              render={({ field }) => (
                <FormItem>
                  <OperatingHoursEditor value={field.value} onChange={field.onChange} />
                  <FormMessage />
                </FormItem>
              )}
            />
          )}
        </div>

        <div className="bg-background sticky bottom-0 flex justify-end gap-2 border-t py-3">
          <Button type="submit" disabled={pending}>
            {pending ? "Saving…" : saved ? "Save changes" : "Add camera and test"}
          </Button>
        </div>
      </form>
    </Form>
  );
}
