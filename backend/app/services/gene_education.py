"""Bilingual explanations backed by a frozen PANTHER/HGNC annotation snapshot."""

import gzip
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.app.core.run_manifest import file_sha256

DISPLAY_TRANSLATIONS = json.loads(
    (Path(__file__).resolve().parents[1] / "resources" / "biology_zh.json").read_text(encoding="utf-8")
)

# Display categories follow PANTHER Protein Class. Enzyme subclasses are kept
# separate so that the metabolic panel is useful to browse rather than one block.
CLASS_TEXT = {
    "PC00197": (
        "跨膜信号受体",
        "接收细胞外信号并将其传入细胞。",
        "Receive extracellular signals and transmit them into the cell.",
    ),
    "PC00207": (
        "细胞间信号分子",
        "在细胞之间传递信息，如分泌的激素或细胞因子。",
        "Carry signals between cells, including secreted hormones and cytokines.",
    ),
    "PC00095": (
        "蛋白活性调节因子",
        "通过与蛋白结合调节其活性，如 G 蛋白调节因子。",
        "Modulate another protein's activity through binding, including G-protein regulators.",
    ),
    "PC00060": (
        "钙结合蛋白",
        "结合钙离子，参与钙信号或钙的储存。",
        "Bind calcium for calcium signalling or storage.",
    ),
    "PC00264": (
        "基因特异性转录调控因子",
        "调节特定基因的转录，包括 DNA 结合转录因子和共调控因子。",
        "Control transcription of specific genes as DNA-binding factors or cofactors.",
    ),
    "PC00009": (
        "DNA 代谢蛋白",
        "参与 DNA 复制、修复、重组或拓扑结构调整。",
        "Participate in DNA replication, repair, recombination or topology changes.",
    ),
    "PC00031": (
        "RNA 代谢蛋白",
        "参与 RNA 的合成、剪接、加工或降解。",
        "Participate in RNA synthesis, splicing, processing or degradation.",
    ),
    "PC00263": (
        "翻译相关蛋白",
        "参与核糖体功能和蛋白质翻译的起始、延伸等步骤。",
        "Support ribosome function and initiation, elongation or other steps of translation.",
    ),
    "PC00227": (
        "跨膜转运蛋白",
        "使离子或分子穿过生物膜，包括通道和转运体。",
        "Move ions or molecules across membranes through channels or transporters.",
    ),
    "PC00219": (
        "转移与载体蛋白",
        "结合并携带分子，协助其在不同位置之间转移。",
        "Bind and carry molecules to support transfer between locations.",
    ),
    "PC00069": (
        "细胞黏附分子",
        "参与细胞与细胞或细胞与基质的黏附。",
        "Mediate adhesion between cells or between cells and the extracellular matrix.",
    ),
    "PC00085": (
        "细胞骨架蛋白",
        "构成或调节细胞骨架，参与形态维持、运动和胞内运输。",
        "Build or regulate the cytoskeleton for cell shape, movement and intracellular transport.",
    ),
    "PC00102": (
        "细胞外基质蛋白",
        "参与细胞外支撑结构及细胞与基质的相互作用。",
        "Contribute to extracellular support structures and cell–matrix interactions.",
    ),
    "PC00070": (
        "细胞连接蛋白",
        "构成或维持细胞间连接与组织屏障。",
        "Build or maintain cell junctions and tissue barriers.",
    ),
    "PC00262": (
        "代谢物转化酶（未细分）",
        "催化代谢物之间的化学转化；当前注释没有指定下列酶学子类。",
        "Catalyse metabolite conversions without a more specific enzyme subclass in this snapshot.",
    ),
    "PC00176": (
        "氧化还原酶",
        "催化电子或氢的转移，参与代谢中的氧化还原反应。",
        "Catalyse electron or hydrogen transfer in metabolic redox reactions.",
    ),
    "PC00220": (
        "转移酶",
        "将化学基团从供体转移到受体，如糖基或磷酸基团。",
        "Transfer chemical groups, such as glycosyl or phosphate groups, between molecules.",
    ),
    "PC00121": (
        "水解酶",
        "利用水分子断裂化学键，参与代谢物分解。",
        "Use water to cleave chemical bonds during metabolite breakdown.",
    ),
    "PC00144": (
        "裂合酶",
        "以非水解、非氧化方式断键，或向双键加成基团。",
        "Cleave bonds without hydrolysis or oxidation, or add groups across double bonds.",
    ),
    "PC00135": (
        "异构酶",
        "催化分子内部重排，将一种异构体转为另一种。",
        "Catalyse rearrangements within a molecule to form another isomer.",
    ),
    "PC00142": (
        "连接酶",
        "将两个分子连接，通常与 ATP 等能量来源的消耗耦联。",
        "Join molecules, typically coupled to consumption of ATP or another energy source.",
    ),
    "PC00090": (
        "防御与免疫蛋白",
        "参与病原识别、防御或免疫反应。",
        "Participate in pathogen recognition, defence or immune responses.",
    ),
    "PC00150": (
        "膜运输与囊泡运输蛋白",
        "参与囊泡形成、分选、运输或膜融合。",
        "Support vesicle formation, sorting, transport or membrane fusion.",
    ),
    "PC00072": (
        "分子伴侣",
        "协助蛋白折叠、组装或稳定，维护蛋白质稳态。",
        "Assist protein folding, assembly or stability to maintain proteostasis.",
    ),
    "PC00237": (
        "病毒或转座元件相关蛋白",
        "与病毒或可移动遗传元件的功能有关。",
        "Have functions associated with viruses or mobile genetic elements.",
    ),
    "PC00226": (
        "支架与衔接蛋白",
        "组织蛋白复合物或连接信号组分，促进相互作用。",
        "Organise protein complexes or connect signalling components to support interactions.",
    ),
    "PC00211": (
        "结构蛋白",
        "提供细胞或组织的结构性支撑。",
        "Provide structural support to cells or tissues.",
    ),
    "PC00210": ("储存蛋白", "结合或储存可供后续使用的物质。", "Bind or store material for subsequent use."),
    "PC00260": (
        "蛋白修饰酶",
        "催化蛋白质的化学修饰或蛋白水解，调节蛋白功能。",
        "Modify proteins chemically or through proteolysis to regulate protein function.",
    ),
    "PC00077": (
        "染色质结合与调控蛋白",
        "参与染色质组成、结合或结构调控，影响 DNA 的可及性。",
        "Build, bind or regulate chromatin and influence access to DNA.",
    ),
}
UNCLASSIFIED = {
    "id": "unclassified",
    "name_zh": "暂无分类注释",
    "name_en": "Not classified in this snapshot",
    "description_zh": "当前数据库快照没有可用的蛋白功能分类，不据基因名称推断其功能。",
    "description_en": (
        "This snapshot has no usable protein-class annotation; function is not inferred from the gene name."
    ),
}


@lru_cache(maxsize=4)
def _read_snapshot(path: str, digest: str) -> dict[str, Any]:
    if file_sha256(Path(path)) != digest:
        raise ValueError("Gene annotation snapshot failed hash validation")
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def load_annotations(root: Path) -> dict[str, Any] | None:
    folder = root / "gene_annotations"
    if not folder.exists():
        return None
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    path = folder / "human.json.gz"
    digest = file_sha256(path)
    if digest != manifest["files"]["human.json.gz"]:
        raise ValueError("Gene annotation snapshot failed hash validation")
    return {**_read_snapshot(str(path), digest), "provenance": manifest}


def classify_gene(
    symbol: str, annotations: dict[str, Any] | None, hgnc_id: str | None = None
) -> dict[str, Any]:
    document = annotations or {}
    identifier = hgnc_id or document.get("symbol_lookup", {}).get(symbol.upper())
    row = document.get("genes", {}).get(identifier, {})
    return {
        "symbol": symbol,
        "approved_symbol": row.get("symbol", symbol),
        "hgnc_id": identifier,
        "name_en": row.get("name_en", ""),
        "name_zh": DISPLAY_TRANSLATIONS["gene_names"].get(row.get("symbol", "")),
        "category_ids": row.get("category_ids") or ["unclassified"],
        "protein_classes": row.get("protein_classes", []),
        "uniprot_ids": row.get("uniprot_ids", []),
    }


def categories_for(genes: list[dict[str, Any]], annotations: dict[str, Any] | None) -> list[dict[str, Any]]:
    counts = Counter(identifier for gene in genes for identifier in set(gene["category_ids"]))
    result = []
    for identifier, count in counts.most_common():
        if identifier == "unclassified":
            result.append({**UNCLASSIFIED, "count": count})
        else:
            zh, description_zh, description_en = CLASS_TEXT[identifier]
            result.append(
                {
                    "id": identifier,
                    "name_zh": zh,
                    "name_en": (annotations or {})["classes"][identifier]["name_en"],
                    "description_zh": description_zh,
                    "description_en": description_en,
                    "count": count,
                }
            )
    return result


TASK_GUIDES = {
    "Fructose degradation (to glucose-3-phosphate)": {
        "name_zh": "果糖降解相关步骤：丙糖磷酸互变",
        "name_en": "Fructose-related triose phosphate interconversion",
        "description_zh": (
            "TPI1 催化磷酸二羟丙酮（DHAP）与甘油醛-3-磷酸（G3P）的可逆互变，将丙糖磷酸连接到糖酵解和糖异生。"
        ),
        "description_en": (
            "TPI1 interconverts dihydroxyacetone phosphate (DHAP) and glyceraldehyde "
            "3-phosphate (G3P), connecting triose phosphates to glycolysis and "
            "gluconeogenesis."
        ),
        "scope_zh": (
            "冻结数据库原名保留 glucose-3-phosphate 字样；本任务仅关联 TPI1 的丙糖磷酸互变，"
            "不表示整条果糖降解途径已被覆盖。"
        ),
        "scope_en": (
            "The frozen task label retains 'glucose-3-phosphate'; its mapped step is "
            "TPI1-mediated triose phosphate interconversion, not the entire fructose "
            "degradation pathway."
        ),
        "source_url": "https://www.uniprot.org/uniprotkb/P60174/entry",
        "source_label": "UniProt · TPI1",
    },
    "Fucosylation (addition of fucose)": {
        "name_zh": "岩藻糖基化（添加岩藻糖）",
        "name_en": "Fucosylation (addition of fucose)",
        "description_zh": (
            "FUT8 将岩藻糖以 α-1,6 键添加到 N-糖链核心的 N-乙酰葡萄糖胺上，参与糖蛋白的核心岩藻糖基化。"
        ),
        "description_en": (
            "FUT8 adds fucose through an alpha-1,6 linkage to the core N-acetylglucosamine of"
            " N-glycans, supporting core fucosylation of glycoproteins."
        ),
        "scope_zh": "当前任务以 FUT8 的核心岩藻糖基化步骤为依据，不代表所有形式的岩藻糖基化。",
        "scope_en": (
            "The mapped evidence concerns FUT8-mediated core fucosylation rather than every "
            "form of fucosylation."
        ),
        "source_url": "https://www.uniprot.org/uniprotkb/Q9BYC5/entry",
        "source_label": "UniProt · FUT8",
    },
    "Malate to pyruvate conversion": {
        "name_zh": "苹果酸转化为丙酮酸",
        "name_en": "Malate to pyruvate conversion",
        "description_zh": (
            "线粒体苹果酸酶 ME2 催化苹果酸氧化脱羧为丙酮酸，释放 CO₂；其 NAD⁺ 依赖反应同时生成 NADH。"
        ),
        "description_en": (
            "Mitochondrial malic enzyme ME2 oxidatively decarboxylates malate to pyruvate and"
            " CO2; its NAD-dependent reaction also produces NADH."
        ),
        "scope_zh": "此处对应 ME2 的代谢步骤，任务分数不能换算为丙酮酸产量或实际通量。",
        "scope_en": (
            "This task maps to the ME2 step; its score cannot be converted to pyruvate "
            "production or measured flux."
        ),
        "source_url": "https://www.uniprot.org/uniprotkb/P23368/entry",
        "source_label": "UniProt · ME2",
    },
    "Mevalonate synthesis": {
        "name_zh": "甲羟戊酸合成",
        "name_en": "Mevalonate synthesis",
        "description_zh": (
            "HMGCR 利用 NADPH 将 HMG-CoA 还原为甲羟戊酸，这是胆固醇及其他异戊二烯类物质合成中的关键步骤。"
        ),
        "description_en": (
            "HMGCR uses NADPH to reduce HMG-CoA to mevalonate, a key step in the biosynthesis"
            " of cholesterol and other isoprenoids."
        ),
        "scope_zh": "当前评分依据 HMGCR 的关联反应，不直接测量胆固醇水平或整条合成途径的活性。",
        "scope_en": (
            "The score uses the mapped HMGCR reaction; it does not measure cholesterol levels"
            " or activity of the complete biosynthetic pathway."
        ),
        "source_url": "https://www.uniprot.org/uniprotkb/P04035/entry",
        "source_label": "UniProt · HMGCR",
    },
    "Presence of the thioredoxin system through the thioredoxin reductase activity": {
        "name_zh": "硫氧还蛋白还原系统",
        "name_en": "Thioredoxin reductase system",
        "description_zh": "TXNRD1 利用 NADPH 将氧化型硫氧还蛋白还原，帮助维持细胞蛋白的氧化还原状态。",
        "description_en": (
            "TXNRD1 uses NADPH to reduce oxidised thioredoxin and helps maintain the redox "
            "state of cellular proteins."
        ),
        "scope_zh": "完整覆盖指当前任务关联的 TXNRD1 已包含在输入中，不等于整个抗氧化系统的功能已得到验证。",
        "scope_en": (
            "Coverage means the mapped TXNRD1 gene is available; it does not validate the "
            "function of the entire antioxidant system."
        ),
        "source_url": "https://www.uniprot.org/uniprotkb/Q16881/entry",
        "source_label": "UniProt · TXNRD1",
    },
    "Reactive oxygen species detoxification (H2O2 to H2O)": {
        "name_zh": "活性氧解毒：过氧化氢分解",
        "name_en": "Reactive oxygen species detoxification: hydrogen peroxide breakdown",
        "description_zh": (
            "过氧化氢酶 CAT 催化 2 H₂O₂ → 2 H₂O + O₂，帮助清除过氧化氢，减轻其对细胞的氧化损伤。"
        ),
        "description_en": (
            "Catalase (CAT) converts 2 H2O2 to 2 H2O and O2, helping remove hydrogen peroxide"
            " and limit oxidative damage."
        ),
        "scope_zh": "任务覆盖的是 CAT 相关的过氧化氢分解步骤，不代表全部活性氧清除途径。",
        "scope_en": (
            "The task covers the CAT-associated hydrogen peroxide step, not all reactive "
            "oxygen species detoxification pathways."
        ),
        "source_url": "https://www.uniprot.org/uniprotkb/P04040/entry",
        "source_label": "UniProt · CAT",
    },
    "Tetrahydrofolate synthesis": {
        "name_zh": "四氢叶酸合成",
        "name_en": "Tetrahydrofolate synthesis",
        "description_zh": (
            "DHFR 利用 NADPH 将二氢叶酸（DHF）还原为四氢叶酸（THF）；"
            "THF 衍生物参与一碳单位转移及核苷酸等分子的合成。"
        ),
        "description_en": (
            "DHFR uses NADPH to reduce dihydrofolate (DHF) to tetrahydrofolate (THF), whose "
            "derivatives support one-carbon transfer and nucleotide biosynthesis."
        ),
        "scope_zh": "此处对应 DHFR 的还原步骤，不表示整个叶酸代谢或核苷酸合成途径均被完整覆盖。",
        "scope_en": (
            "This maps to the DHFR reduction step rather than full coverage of folate "
            "metabolism or nucleotide biosynthesis."
        ),
        "source_url": "https://www.uniprot.org/uniprotkb/P00374/entry",
        "source_label": "UniProt · DHFR",
    },
}


# These are display translations of the frozen labels, not new biological
# annotations. Preserve the seven reaction-specific, sourced explanations above.
for _task_id, _name_zh in DISPLAY_TRANSLATIONS["task_names"].items():
    TASK_GUIDES.setdefault(
        _task_id,
        {
            "name_zh": _name_zh,
            "name_en": _task_id,
            "description_zh": (
                f"该任务对应“{_name_zh}”，汇总知识库中关联反应获得的表达支持。"
            ),
            "description_en": (
                f"This task describes {_task_id} and summarises expression support "
                "for its associated reactions in the knowledge base."
            ),
            "scope_zh": (
                "中文译名按冻结知识库任务名称整理；任务分数须结合关联基因覆盖解读，"
                "不直接表示实测代谢通量或整个生物过程的活性。"
            ),
            "scope_en": (
                "The display translation follows the frozen task label. Interpret the score "
                "with associated-gene coverage; it is not measured flux or validation "
                "of the complete biological process."
            ),
            "source_url": "https://sccellfie.readthedocs.io/en/latest/",
            "source_label": "scCellFie · human Recon2",
        },
    )
