export interface PageParams {
  page: number;
  size: number;
}

export interface PagedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface ResponseEnvelope<T> {
  code: string | number;
  message: string;
  data: T;
}
