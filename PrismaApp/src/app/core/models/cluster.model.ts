
export interface ClusterListItem {
  
  clusterRunId: number;
  
  clusterId: number;
  
  labelText: string;
  
  topTfidfTerms: string[];
  
  topEntities: string[];
  
  articleCount: number;
  
  outletCount: number;
  
  dateFrom: string;
  
  dateTo: string;
  
  isEventCluster: boolean;
  
  parentClusterId: number | null;
}


export interface PaginatedResult<T> {
  items: T[];
  totalCount: number;
  page: number;
  pageSize: number;
}
