export interface DispatchPolicy {
  id: string;
  name: string;
  description?: string;
  requiresServiceZones?: boolean;
}

export const DISPATCH_POLICIES: DispatchPolicy[] = [
  {
    id: 'nearest',
    name: 'Nearest',
    description: 'Dispatch the nearest available unit to the incident',
    requiresServiceZones: false
  },
  {
    id: 'firebeats',
    name: 'Firebeats',
    description: 'Dispatch units based on predefined service zones',
    requiresServiceZones: true
  }
];

export const getDispatchPolicy = (id: string): DispatchPolicy | undefined => {
  return DISPATCH_POLICIES.find(policy => policy.id === id);
};