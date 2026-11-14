import { api } from "./api";
import type { DrugRecord, Medication, MedicationInput, Paginated, Patient, PatientInput } from "./types";

export const listPatients = (page = 1) => api<Paginated<Patient>>(`/patients/?page=${page}`);

export const getPatient = (id: number) => api<Patient>(`/patients/${id}/`);

export const createPatient = (data: PatientInput) =>
  api<Patient>("/patients/", { method: "POST", body: JSON.stringify(data) });

/** The backend paginates this endpoint (PAGE_SIZE 20, max 100). Accepts a plain array too, so a schema change cannot crash the screen. */
export async function listMedications(patientId: number): Promise<Medication[]> {
  const res = await api<Paginated<Medication> | Medication[]>(`/patients/${patientId}/medications/?page_size=100`);
  return Array.isArray(res) ? res : res.results;
}

export const addMedication = (patientId: number, data: MedicationInput) =>
  api<Medication>(`/patients/${patientId}/medications/`, { method: "POST", body: JSON.stringify(data) });

/**
 * Turn a resolved generic name into the Drug id the medications API expects.
 * Exact (case-insensitive) match only: a near-miss returns null and the medicine is saved as "unresolved"
 * rather than being linked to the wrong drug (rule.md §1: never guess).
 *
 * GET /api/drugs/ currently ignores `?search=` (DrugFilter exists but is not set as `filterset_class` on DrugListView),
 * so this follows the pages until it finds the exact name. Once the backend wires the filter, the first page is enough.
 */
export async function findDrugId(generic: string): Promise<number | null> {
  const wanted = generic.trim().toLowerCase();
  if (!wanted) return null;
  const MAX_PAGES = 10;
  for (let page = 1; page <= MAX_PAGES; page++) {
    const res = await api<Paginated<DrugRecord>>(
      `/drugs/?search=${encodeURIComponent(wanted)}&page_size=100&page=${page}`,
    );
    const hit = res.results.find((d) => d.generic_name.trim().toLowerCase() === wanted);
    if (hit) return hit.id;
    if (!res.next) break;
  }
  return null;
}