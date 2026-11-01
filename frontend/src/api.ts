import axios, { AxiosError, type AxiosResponse } from 'axios';
import type {
  ApiErrorBody,
  ApiListResponse,
  ApiResponse,
  DashboardSummary,
  DataRecord,
} from './types';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api',
  headers: { Accept: 'application/json' },
});

export class ApiRequestError extends Error {
  code?: string;
  details?: unknown;

  constructor(message: string, code?: string, details?: unknown) {
    super(message);
    this.name = 'ApiRequestError';
    this.code = code;
    this.details = details;
  }
}

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as ApiErrorBody | undefined;
    return body?.error?.message || error.message || 'The request could not be completed.';
  }
  return error instanceof Error ? error.message : 'The request could not be completed.';
}

function throwApiError(error: unknown): never {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as ApiErrorBody | undefined;
    throw new ApiRequestError(
      body?.error?.message || error.message || 'The request could not be completed.',
      body?.error?.code,
      body?.error?.details,
    );
  }
  throw error;
}

async function throwDownloadError(error: unknown): Promise<never> {
  if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
    try {
      const body = JSON.parse(await error.response.data.text()) as ApiErrorBody;
      throw new ApiRequestError(
        body.error?.message || error.message || 'The download could not be completed.',
        body.error?.code,
        body.error?.details,
      );
    } catch (parseError) {
      if (parseError instanceof ApiRequestError) throw parseError;
    }
  }
  return throwApiError(error);
}

async function request<T>(operation: () => Promise<AxiosResponse<T>>): Promise<T> {
  try {
    const response = await operation();
    return response.data;
  } catch (error) {
    return throwDownloadError(error);
  }
}

export const getDashboardSummary = () =>
  request(() => api.get<ApiResponse<DashboardSummary>>('/dashboard/summary'))
    .then((response) => response.data);

export const getRecords = (endpoint: string) =>
  request(() => api.get<ApiListResponse<DataRecord>>(endpoint))
    .then((response) => response.data);

export const runForecast = (term_code: string) =>
  request(() => api.post('/forecast/run', { term_code }));

export const generateSections = (term_code: string) =>
  request(() => api.post('/allocations/sections', { term_code }));

export const allocateFaculty = (term_code: string) =>
  request(() => api.post('/allocations/faculty', { term_code }));

export const validateDataset = () => request(() => api.post('/validation/run'));

export const generateSyntheticData = (mode: 'starter' | 'full', seed: number) =>
  request(() => api.post('/data/generate', { mode, seed }));

export async function downloadFile(endpoint: string, fallbackName: string): Promise<void> {
  try {
    const response = await api.get<Blob | string | DataRecord>(endpoint, {
      responseType: 'blob',
      headers: { Accept: '*/*' },
    });
    const disposition = response.headers['content-disposition'] as string | undefined;
    const filename = disposition?.match(/filename="?([^";]+)"?/i)?.[1] || fallbackName;
    const blob = response.data instanceof Blob
      ? response.data
      : new Blob([typeof response.data === 'string' ? response.data : JSON.stringify(response.data, null, 2)], {
          type: endpoint.endsWith('.csv') ? 'text/csv' : 'application/json',
        });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    return throwDownloadError(error);
  }
}

export async function downloadReport(): Promise<void> {
  try {
    const response = await api.get<Blob | string | DataRecord>('/reports', {
      responseType: 'blob',
      headers: { Accept: 'text/csv, application/json' },
    });
    const contentType = (response.headers['content-type'] as string | undefined) || '';
    const extension = contentType.includes('csv') ? 'csv' : 'json';
    const disposition = response.headers['content-disposition'] as string | undefined;
    const filename = disposition?.match(/filename="?([^";]+)"?/i)?.[1] || `academic-report.${extension}`;
    const blob = response.data instanceof Blob
      ? response.data
      : new Blob([typeof response.data === 'string' ? response.data : JSON.stringify(response.data, null, 2)], {
          type: contentType || 'application/json',
        });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    return throwDownloadError(error);
  }
}

export async function resolveException(id: string | number): Promise<void> {
  await request(() => api.patch(`/exceptions/${encodeURIComponent(String(id))}/resolve`));
}

export function isNetworkError(error: unknown): error is AxiosError {
  return axios.isAxiosError(error) && !error.response;
}
