import type { CellLine } from '../types/run'

export interface CellBackground {
  id: CellLine
  name: string
  type_zh: string
  type_en: string
  growth_zh: string
  growth_en: string
  origin_zh: string
  origin_en: string
  features_zh: string
  features_en: string
  uses_zh: string
  uses_en: string
  sources: { label: string; url: string }[]
}

// Reviewed against Cellosaurus and ATCC on 2026-10-11. These descriptions
// do not identify the exact engineered clone in an experimental dataset.
export const cellBackgrounds: Record<CellLine, CellBackground> = {
  K562: {
    id: 'K562', name: 'K-562',
    type_zh: '髓系白血病细胞系', type_en: 'Myeloid leukemia cell line',
    growth_zh: '悬浮生长', growth_en: 'Suspension',
    origin_zh: '来源于慢性髓性白血病急变期患者的胸腔积液，是人类造血系统肿瘤细胞系。',
    origin_en: 'A human hematopoietic cancer cell line established from pleural effusion in chronic myeloid leukemia blast crisis.',
    features_zh: '具有 BCR–ABL1 融合及红系分化潜能；保留造血肿瘤背景下的增殖与基因调控特征。',
    features_en: 'Carries the BCR–ABL1 fusion and has erythroid differentiation potential, providing a hematopoietic cancer context for proliferation and gene regulation.',
    uses_zh: '常用于白血病机制、红系分化、基因调控及自然杀伤细胞活性研究。',
    uses_en: 'Used to study leukemia, erythroid differentiation, gene regulation and natural killer cell activity.',
    sources: [{ label: 'Cellosaurus · CVCL_0004', url: 'https://www.cellosaurus.org/CVCL_0004' }, { label: 'ATCC · CCL-243', url: 'https://www.atcc.org/products/ccl-243' }],
  },
  RPE1: {
    id: 'RPE1', name: 'hTERT-RPE1',
    type_zh: '永生化视网膜色素上皮细胞系', type_en: 'Immortalized retinal pigment epithelial cell line',
    growth_zh: '贴壁生长', growth_en: 'Adherent',
    origin_zh: '来自人类视网膜色素上皮，通过表达端粒酶逆转录酶 hTERT 获得持续增殖能力。',
    origin_en: 'Derived from human retinal pigment epithelium and immortalized by expression of telomerase reverse transcriptase, hTERT.',
    features_zh: '正常组织来源，具有上皮样形态和近二倍体核型；永生化细胞与原代视网膜组织仍有差异。',
    features_en: 'A normal-tissue-derived line with epithelial-like morphology and a near-diploid karyotype; immortalized cells still differ from primary retinal tissue.',
    uses_zh: '常用于细胞周期、染色体稳定性和纤毛形成研究，也用于基因功能筛选。',
    uses_en: 'Used to study the cell cycle, chromosome stability and ciliogenesis, as well as in gene-function screens.',
    sources: [{ label: 'Cellosaurus · CVCL_4388', url: 'https://www.cellosaurus.org/CVCL_4388' }, { label: 'ATCC · CRL-4000', url: 'https://www.atcc.org/products/crl-4000' }],
  },
  Jurkat: {
    id: 'Jurkat', name: 'Jurkat',
    type_zh: 'T 淋巴细胞白血病细胞系', type_en: 'T-cell leukemia cell line',
    growth_zh: '悬浮生长', growth_en: 'Suspension',
    origin_zh: '来源于 T 细胞急性淋巴细胞白血病患者的外周血，是人类 T 淋巴细胞肿瘤细胞系。',
    origin_en: 'A human T-cell cancer line derived from peripheral blood of a patient with T-cell acute lymphoblastic leukemia.',
    features_zh: '具有 T 淋巴细胞背景，可用于观察受体刺激后的信号转导；不同亚克隆的信号缺陷与反应有所不同。',
    features_en: 'Provides a T-lymphocyte context for receptor-induced signaling; signaling defects and responses vary among subclones.',
    uses_zh: '常用于 T 细胞受体信号、免疫激活、细胞因子调控和凋亡研究。',
    uses_en: 'Used to study T-cell receptor signaling, immune activation, cytokine regulation and apoptosis.',
    sources: [{ label: 'Cellosaurus · CVCL_0065', url: 'https://www.cellosaurus.org/CVCL_0065' }, { label: 'ATCC · E6-1 亚克隆 / TIB-152', url: 'https://www.atcc.org/products/tib-152' }],
  },
  HepG2: {
    id: 'HepG2', name: 'Hep-G2',
    type_zh: '肝母细胞瘤来源细胞系', type_en: 'Hepatoblastoma-derived cell line',
    growth_zh: '贴壁生长', growth_en: 'Adherent',
    origin_zh: '来源于人类肝脏肿瘤。早期被称为肝细胞癌细胞系，Cellosaurus 依据后续研究将其修正为肝母细胞瘤来源。',
    origin_en: 'Derived from a human liver tumor. Initially described as hepatocellular carcinoma, it is classified by Cellosaurus as hepatoblastoma-derived following later studies.',
    features_zh: '具有上皮样形态，可表达白蛋白等肝相关蛋白并保留部分肝代谢特征；代谢功能与正常成人肝细胞有差异。',
    features_en: 'Has epithelial-like morphology, expresses liver-associated proteins such as albumin and retains some hepatic metabolic features; its metabolism differs from normal adult hepatocytes.',
    uses_zh: '常用于肝相关代谢、蛋白分泌、氧化应激与毒理学研究。',
    uses_en: 'Used to study liver-associated metabolism, protein secretion, oxidative stress and toxicology.',
    sources: [{ label: 'Cellosaurus · CVCL_0027', url: 'https://www.cellosaurus.org/CVCL_0027' }, { label: 'ATCC · HB-8065', url: 'https://www.atcc.org/products/hb-8065' }],
  },
}

export function getCellBackground(cellLine?: string): CellBackground | undefined {
  return cellLine && Object.prototype.hasOwnProperty.call(cellBackgrounds, cellLine)
    ? cellBackgrounds[cellLine as CellLine]
    : undefined
}
