import type { CalibrationStatus } from '@/features/motor/api/motor-api'

export const SPEC_STATUS: Record<CalibrationStatus, { label: string; className: string; dot: string }> = {
  actual: { label: 'актуальна', className: 'bg-[#79de83]/15 text-[#79de83]', dot: 'border-[#79de83]/50 bg-[#79de83]/20 text-[#c9f5cd]' },
  stale: { label: 'устарела', className: 'bg-[#f2cf87]/15 text-[#f2cf87]', dot: 'border-[#f2cf87]/50 bg-[#f2cf87]/15 text-[#f8e6bd]' },
  failed: { label: 'не пройдена', className: 'bg-[#ff8f84]/15 text-[#ff8f84]', dot: 'border-[#ff8f84]/50 bg-[#ff8f84]/15 text-[#ffc9c3]' },
  missing: { label: 'не выполнена', className: 'bg-white/8 text-white/55', dot: 'border-white/12 bg-white/4 text-white/55' },
  planned: { label: 'в разработке', className: 'bg-white/6 text-white/40', dot: 'border-white/8 bg-transparent text-white/30' },
}
