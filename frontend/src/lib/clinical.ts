import { api } from "./api";
import type { DrugSuggestion, Medication, MedicationInput, Paginated, Patient, PatientInput } from "./types";

export const listPatients = (page = 1) => api<Paginated<Patient>>(`/patients/?page=${page}`);

export const getPatient = (id: number) => api<Patient>(`/patients/${id}/`);

export const createPatient = (data: PatientInput) =>
  api<Patient>("/patients/", { method: "POST", body: JSON.stringify(data) });

export const listMedications = (patientId: number) => api<Medication[]>(`/patients/${patientId}/medications/`);

export const addMedication = (patientId: number, data: MedicationInput) =>
  api<Medication>(`/patients/${patientId}/medications/`, { method: "POST", body: JSON.stringify(data) });

export async function searchDrugs(q: string, signal?: AbortSignal): Promise<DrugSuggestion[]> {
  const res = await api<{ results: DrugSuggestion[] }>(`/drugs/search/?q=${encodeURIComponent(q)}`, { signal });
  return res.results;
}