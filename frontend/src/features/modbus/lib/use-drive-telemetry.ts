import { useQuery } from '@tanstack/react-query'
import { fetchModbusTorqueTelemetry } from '../api/modbus-api'
import { useModbusStore } from './use-modbus-store'

export function useDriveTelemetry(interval: number | false = false) {
  const status = useModbusStore((state) => state.connectionStatus)
  const slaveId = useModbusStore((state) => state.driveAddresses[state.selectedSide])
  return useQuery({
    queryKey: ['modbus-monitor', status?.port, slaveId],
    queryFn: () => fetchModbusTorqueTelemetry(slaveId),
    enabled: status?.connected === true,
    retry: false,
    refetchInterval: status?.connected ? interval : false,
    refetchOnWindowFocus: false,
    gcTime: 0,
  })
}
