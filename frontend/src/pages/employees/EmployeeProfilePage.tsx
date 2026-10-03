import { ArrowLeft, ShieldAlert, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import type { AttendanceDayOut } from "@/api/generated/model";
import { mediaUrl } from "@/api/media";
import { AttendanceCalendar } from "@/components/attendance/AttendanceCalendar";
import { AttendanceDayDialog } from "@/components/attendance/AttendanceDayDialog";
import { MonthPicker } from "@/components/attendance/MonthPicker";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { ErrorState } from "@/components/common/ErrorState";
import { SecureImage } from "@/components/common/SecureImage";
import { StatusBadge } from "@/components/common/StatusBadge";
import { EmployeeForm } from "@/components/employees/EmployeeForm";
import { EnrollPanel } from "@/components/employees/EnrollPanel";
import { FaceGallery } from "@/components/employees/FaceGallery";
import { LeavesPanel } from "@/components/employees/LeavesPanel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth, useTimezone } from "@/hooks/useAuth";
import { useEmployee, useEmployeeMutations } from "@/hooks/useEmployees";
import { useUrlState } from "@/hooks/useUrlState";
import { todayIn } from "@/lib/format";
import { showError } from "@/lib/forms";
import { employeeStatusLabel } from "@/lib/labels";
import { currentMonth } from "@/lib/month";
import { Permission } from "@/lib/permissions";
import { NotFoundPage } from "@/pages/errors/NotFoundPage";

/** §13 screen 5: details, face gallery, enroll, attendance history, leave. */
export function EmployeeProfilePage() {
  const { employeeId } = useParams();
  const id = Number(employeeId);
  const { can } = useAuth();
  const timezone = useTimezone();
  const navigate = useNavigate();
  const url = useUrlState();
  const employee = useEmployee(Number.isInteger(id) ? id : null);
  const { update, remove, eraseBiometrics } = useEmployeeMutations();
  const [confirm, setConfirm] = useState<"erase" | "delete" | null>(null);
  const [selectedDay, setSelectedDay] = useState<AttendanceDayOut | null>(null);
  const tab = url.get("tab") ?? "details";
  const month = url.get("month") ?? currentMonth(todayIn(timezone));

  if (employee.isPending) return <Skeleton className="h-96" />;
  if (employee.isError) {
    return (employee.error as { status?: number }).status === 404 ? (
      <NotFoundPage />
    ) : (
      <ErrorState error={employee.error} onRetry={() => void employee.refetch()} />
    );
  }
  const data = employee.data.data;
  const status = employeeStatusLabel[data.status];

  return (
    <>
      <Button asChild variant="ghost" size="sm" className="mb-2 -ml-2">
        <Link to="/employees">
          <ArrowLeft aria-hidden /> Employees
        </Link>
      </Button>
      <div className="mb-6 flex flex-wrap items-center gap-4">
        <SecureImage
          src={data.enrolled_photos ? mediaUrl.employeePhoto(data.id) : null}
          alt={`Photo of ${data.full_name}`}
          fallbackName={data.full_name}
          className="size-16 rounded-full text-lg"
        />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{data.full_name}</h1>
          <p className="text-muted-foreground text-sm">
            <span className="font-mono">{data.employee_code}</span>
            {data.department_name && ` · ${data.department_name}`}
            {data.shift_name && ` · ${data.shift_name}`}
          </p>
        </div>
        <StatusBadge label={status.label} tone={status.tone} />
        <StatusBadge
          label={data.enrolled_photos ? `Enrolled ${data.enrolled_photos} photos` : "Not enrolled"}
          tone={data.enrollment_complete ? "ok" : data.enrolled_photos ? "warn" : "neutral"}
        />
      </div>

      <Tabs value={tab} onValueChange={(value) => url.set({ tab: value, month: url.get("month") })}>
        <TabsList className="flex-wrap">
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="faces">Face gallery</TabsTrigger>
          <TabsTrigger value="enroll">Enroll</TabsTrigger>
          <TabsTrigger value="attendance">Attendance history</TabsTrigger>
          <TabsTrigger value="leave">Leave</TabsTrigger>
        </TabsList>

        <TabsContent value="details" className="space-y-6">
          <Card>
            <CardContent className="pt-6">
              <EmployeeForm
                key={data.id}
                employee={data}
                submitLabel="Save changes"
                onSubmit={async (payload) => {
                  // The employee code is fixed once created.
                  const { employee_code, ...changes } = payload;
                  await update.mutateAsync({ id: data.id, body: changes });
                }}
              />
            </CardContent>
          </Card>
          <Card className="border-destructive/40">
            <CardHeader>
              <CardTitle className="text-base">Biometric data and record removal</CardTitle>
              <CardDescription>
                Erasing removes every face photo, embedding and event snapshot of this employee permanently (right to
                erasure). Deleting also removes the employee; attendance history is kept.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {can(Permission.biometricsErase) && (
                <Button variant="outline" onClick={() => setConfirm("erase")}>
                  <ShieldAlert aria-hidden /> Erase biometric data
                </Button>
              )}
              <Button variant="destructive" onClick={() => setConfirm("delete")}>
                <Trash2 aria-hidden /> Delete employee
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="faces">
          <FaceGallery employeeId={data.id} onEnroll={() => url.set({ tab: "enroll" })} />
        </TabsContent>

        <TabsContent value="enroll">
          <EnrollPanel employee={data} />
        </TabsContent>

        <TabsContent value="attendance" className="space-y-4">
          <MonthPicker
            month={month}
            onChange={(next) => url.set({ tab: "attendance", month: next })}
            max={currentMonth(todayIn(timezone))}
          />
          <AttendanceCalendar employeeId={data.id} month={month} onSelect={setSelectedDay} />
        </TabsContent>

        <TabsContent value="leave">
          <LeavesPanel employeeId={data.id} />
        </TabsContent>
      </Tabs>

      <AttendanceDayDialog day={selectedDay} onOpenChange={(open) => !open && setSelectedDay(null)} />

      <ConfirmDialog
        open={confirm === "erase"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Erase all biometric data?"
        description={
          <p>
            Every face photo, embedding and event snapshot of <strong>{data.full_name}</strong> is deleted permanently and
            they are no longer recognised. This cannot be undone.
          </p>
        }
        confirmLabel="Erase permanently"
        requireText={data.employee_code}
        pending={eraseBiometrics.isPending}
        onConfirm={async () => {
          try {
            await eraseBiometrics.mutateAsync({ id: data.id, code: data.employee_code });
            setConfirm(null);
          } catch (error) {
            showError(error);
          }
        }}
      />
      <ConfirmDialog
        open={confirm === "delete"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Delete this employee?"
        description={
          <p>
            <strong>{data.full_name}</strong> is removed and all their biometric data is erased permanently. Their past
            attendance stays in reports.
          </p>
        }
        confirmLabel="Delete employee"
        requireText={data.employee_code}
        pending={remove.isPending}
        onConfirm={async () => {
          try {
            await remove.mutateAsync({ id: data.id, code: data.employee_code });
            navigate("/employees", { replace: true });
          } catch (error) {
            showError(error);
          }
        }}
      />
    </>
  );
}
