import { listExperiments } from './experiments'
import { measuredApi } from './measured'
import { isMockEnabled } from './mockFlag'
import { collectRecordPages, measuredRecord, predictedRecord } from '../utils/researchRecords'

export async function listResearchRecords(signal?: AbortSignal) {
  const mock = isMockEnabled()
  const [predicted, measured] = await Promise.all([
    collectRecordPages((limit, offset) => listExperiments({ limit, offset, q: '', status: 'all' }, signal), signal),
    mock ? Promise.resolve([]) : collectRecordPages((limit, offset) => measuredApi.list(limit, offset, signal), signal),
  ])
  return [...predicted.map(record => predictedRecord(record, mock)), ...measured.map(measuredRecord)]
}
