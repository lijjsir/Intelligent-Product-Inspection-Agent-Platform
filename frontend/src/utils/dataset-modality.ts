import type { DatasetModality, DatasetSampleType } from "@/types/dataset.types";

const modalityOrder: DatasetSampleType[] = ["image", "video", "text"];

export function normalizeDatasetModality(value: string | string[]): DatasetModality {
  const source = Array.isArray(value)
    ? value
    : String(value || "")
      .replace(/image_text/g, "image+text")
      .replace(/[|/, ]+/g, "+")
      .split("+");
  const unique = new Set(
    source
      .map((item) => String(item).trim().toLowerCase())
      .filter((item): item is DatasetSampleType => ["image", "video", "text"].includes(item)),
  );
  return modalityOrder.filter((item) => unique.has(item)).join("+") as DatasetModality;
}

export function splitDatasetModality(value: string | null | undefined): DatasetSampleType[] {
  const normalized = normalizeDatasetModality(value || "");
  return normalized ? normalized.split("+") as DatasetSampleType[] : [];
}

export function datasetSupportsSampleType(modality: string | null | undefined, sampleType: DatasetSampleType): boolean {
  return splitDatasetModality(modality).includes(sampleType);
}

export function datasetModalityLabel(modality: string | null | undefined): string {
  const parts = splitDatasetModality(modality);
  if (!parts.length) return "-";
  const labels: Record<DatasetSampleType, string> = {
    image: "图片",
    video: "视频",
    text: "文本",
  };
  return parts.map((item) => labels[item]).join(" + ");
}
