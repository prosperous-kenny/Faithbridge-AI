export type HealthStatus = {
  status: string;
  service: string;
};

export type ReadinessStatus = HealthStatus & {
  database: "up" | "down";
};

export type DashboardStats = {
  organizations: number;
  users: number;
  programs: number;
  beneficiaries: number;
  assistance_requests: number;
  donations: number;
  placements: number;
  impact_events: number;
};

export type ServiceStatus = {
  name: string;
  url: string;
  ok: boolean;
  detail: string;
};

export type SystemStatus = {
  services: ServiceStatus[];
  stats: DashboardStats | null;
  checkedAt: string;
};
