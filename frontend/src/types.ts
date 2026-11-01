export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
}

export interface ForecastPoint {
  term: string;
  actual: number;
  predicted: number;
}

export interface CountPoint {
  category: string;
  count: number;
}

export interface FacultyWorkloadPoint {
  faculty: string;
  assigned_hours: number;
  max_hours: number;
}

export interface CapacityPoint {
  course: string;
  capacity: number;
  enrollment: number;
}

export interface StatusPoint {
  status: string;
  count: number;
}

export interface UnmetDemandPoint {
  course: string;
  unmet: number;
}

export interface DashboardSummary {
  programs: number;
  courses: number;
  students: number;
  faculty: number;
  predicted_enrollment: number;
  sections: number;
  unmet_demand: number;
  allocation_success_rate: number;
  forecast_history: ForecastPoint[];
  demand_distribution: CountPoint[];
  faculty_workload: FacultyWorkloadPoint[];
  capacity_utilization: CapacityPoint[];
  faculty_status: StatusPoint[];
  unmet_by_course: UnmetDemandPoint[];
}

export type DataRecord = Record<string, unknown>;

export interface ApiListResponse<T> {
  data: T[];
}

export interface ApiResponse<T> {
  data: T;
}

export interface ActionNotice {
  kind: 'success' | 'error';
  message: string;
}
