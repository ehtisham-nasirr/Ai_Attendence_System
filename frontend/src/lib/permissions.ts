/** Permission names as returned by /auth/me (backend core/security.py, requirements §4). */
export const Permission = {
  usersManage: "users:manage",
  settingsManage: "settings:manage",
  camerasManage: "cameras:manage",
  employeesManage: "employees:manage",
  biometricsErase: "biometrics:erase",
  liveView: "live:view",
  attendanceView: "attendance:view",
  attendanceCorrect: "attendance:correct",
  correctionsRequest: "corrections:request",
  unknownFacesReview: "unknown_faces:review",
  unknownFacesAssign: "unknown_faces:assign",
  eventsView: "events:view",
  eventsVoid: "events:void",
  reportsExport: "reports:export",
  auditView: "audit:view",
  dashboardView: "dashboard:view",
  organizationView: "organization:view",
} as const;

export type PermissionName = (typeof Permission)[keyof typeof Permission];
