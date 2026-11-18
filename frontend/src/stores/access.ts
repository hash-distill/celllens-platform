import { ref } from 'vue'
export interface AccessSession {mode:'local'|'private'|'public';authenticated:boolean;configured:boolean;read_only:boolean;public_result_ids:string[]}
export const accessSession=ref<AccessSession|null>(null)
