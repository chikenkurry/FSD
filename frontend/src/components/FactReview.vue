<template>
  <section class="fact-review" aria-labelledby="facts-heading">
    <h3 id="facts-heading">Supporting facts</h3>
    <p class="helper-text">These details describe the options. Exact, cited findings can be used automatically. Correct a value or ask research to check it again if needed. This optional review never blocks publishing.</p>
    <article v-for="option in options" :key="option.id || option.title" class="fact-option">
      <h4>{{ option.title }}</h4>
      <div v-for="definition in definitions" :key="definition.criterion" class="fact-row" :data-testid="`fact-${option.title}-${definition.criterion}`">
        <div class="fact-heading"><strong>{{ factLabel(definition.criterion) }}</strong><span class="badge">{{ status(option,definition) }}</span></div>
        <label>Fact value
          <select v-if="definition.valueType === 'boolean'" :value="fact(option,definition)?.value || ''" @change="edit(option,definition,($event.target as HTMLSelectElement).value)"><option value="">Unknown</option><option value="true">Yes</option><option value="false">No</option></select>
          <textarea v-else-if="definition.valueType === 'tag_set'" :value="displayValue(option,definition)" placeholder="One attribute per line" @input="edit(option,definition,($event.target as HTMLTextAreaElement).value)"></textarea>
          <input v-else :value="displayValue(option,definition)" :inputmode="['number','decimal'].includes(definition.valueType) ? 'decimal' : 'text'" placeholder="Enter a verified value" @input="edit(option,definition,($event.target as HTMLInputElement).value)" />
        </label>
        <p v-if="definition.unit" class="helper-text">Unit: {{ definition.unit }}</p>
        <p v-if="definition.valueType === 'tag_set'" class="helper-text">List one attribute per line. Values come from evidence and do not need to match the question’s choices.</p>
        <p v-if="fact(option,definition)?.context?.stale" class="helper-text">The option changed. This old value will need fresh evidence before it can be used.</p>
        <p v-if="fact(option,definition)?.context?.source_text" class="helper-text evidence">Source excerpt: {{ fact(option,definition)?.context?.source_text }}</p>
        <p v-if="fact(option,definition)?.context?.qualifier && fact(option,definition)?.context?.qualifier !== 'exact'" class="helper-text">This finding has conditions ({{ fact(option,definition)?.context?.qualifier }}). Verify and correct the value before using it.</p>
        <p v-if="fact(option,definition)?.context?.reason" class="helper-text">Research note: {{ fact(option,definition)?.context?.reason }}</p>
        <div v-if="alternatives(option,definition).length" class="alternatives"><p>Conflicting findings need your decision:</p><div v-for="(claim,index) in alternatives(option,definition)" :key="index"><p>{{ claim.context.source_text }}</p><button type="button" class="btn-quiet btn-small" @click="choose(option,definition,claim)">Use this finding</button></div></div>
        <ul v-if="fact(option,definition)?.context?.sources?.length" class="sources"><li v-for="source in fact(option,definition)?.context?.sources" :key="source.url"><a v-if="safeUrl(source.url)" :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.title || source.url }}</a></li></ul>
        <label>Source or verification note <span class="optional">(optional)</span><input :value="fact(option,definition)?.source || ''" placeholder="Website, menu, or details you checked" @input="source(option,definition,($event.target as HTMLInputElement).value)" /></label>
        <button v-if="fact(option,definition)?.context?.corrected && !fact(option,definition)?.context?.reviewed" type="button" :disabled="!validFact(fact(option,definition),definition)" @click="approve(option,definition)">Use my correction</button>
        <details class="research-again"><summary>Research or correct this fact</summary>
          <label>What should research check? <span class="optional">(optional)</span><textarea :value="notes[key(option,definition)] || ''" maxlength="1000" placeholder="e.g. Check the current menu; the previous price seems outdated." @input="notes[key(option,definition)]=($event.target as HTMLTextAreaElement).value"></textarea></label>
          <button type="button" :disabled="researching" @click="emit('research',option,definition,notes[key(option,definition)] || '')">{{ researching ? 'Researching…' : 'Research again' }}</button>
          <p class="helper-text">Your correction is kept if you edit it while research runs. Missing or conflicting evidence stays unresolved.</p>
        </details>
      </div>
    </article>
  </section>
</template>
<script setup lang="ts">
import { reactive } from 'vue';
import type { DecisionOption, Fact, FactDefinition, Form, ResearchedFact } from '@/types/form';
import { factSignature, factStatus, tagValues, validFact } from '@/services/optionFacts';
import { factLabel } from '@/services/facts';
import { researchedFact } from '@/services/research';
const props = defineProps<{ form:Form; options:DecisionOption[]; definitions:FactDefinition[]; researching:boolean }>();
const emit = defineEmits<{(event:'research',option:DecisionOption,definition:FactDefinition,note:string):void}>();
const notes = reactive<Record<string,string>>({});
const key = (o:DecisionOption,d:FactDefinition) => `${o.id || o.title}:${d.criterion}`;
const fact = (o:DecisionOption,d:FactDefinition) => o.facts.find(f => f.criterion === d.criterion);
const displayValue = (o:DecisionOption,d:FactDefinition) => d.valueType === 'tag_set' ? tagValues(fact(o,d)?.value || '').join('\n') : fact(o,d)?.value || '';
function ensure(o:DecisionOption,d:FactDefinition):Fact { let row=fact(o,d); if(!row){row={criterion:d.criterion,value:'',valueType:d.valueType,unit:d.unit,source:'',status:'unknown'};o.facts.push(row);}return row; }
function edit(o:DecisionOption,d:FactDefinition,value:string){const row=ensure(o,d);row.value=d.valueType==='tag_set' ? JSON.stringify(value.split(/\r?\n/).map(v=>v.trim()).filter(Boolean)) : value;row.valueType=d.valueType;row.unit=d.unit;row.status='estimated';row.context={...row.context,stale:false,corrected:true,reviewed:false,verification:undefined,valid_until:undefined,alternatives:[],input_signature:factSignature(props.form,o,d)};}
function source(o:DecisionOption,d:FactDefinition,value:string){const row=ensure(o,d);row.source=value;row.status='estimated';row.context={...row.context,corrected:true,reviewed:false,verification:undefined};}
function approve(o:DecisionOption,d:FactDefinition){const row=ensure(o,d);row.status='confirmed';row.context={...row.context,reviewed:true,verification:'organiser',input_signature:factSignature(props.form,o,d)};}
function status(o:DecisionOption,d:FactDefinition){const row=fact(o,d);return row?.context?.stale?'Needs updating':factStatus(row)==='confirmed'?(row?.context?.reviewed?'Corrected':'Sourced'):row?.value?'Unverified':'Missing';}
function alternatives(o:DecisionOption,d:FactDefinition):ResearchedFact[]{const rows=fact(o,d)?.context?.alternatives;return Array.isArray(rows) ? rows as ResearchedFact[] : [];}
function choose(o:DecisionOption,d:FactDefinition,claim:ResearchedFact){const row=researchedFact(claim,factSignature(props.form,o,d));if(validFact(row,d)){row.status='confirmed';row.context={...row.context,reviewed:true,verification:'organiser'};}o.facts=[...o.facts.filter(f=>f.criterion!==d.criterion),row];}
function safeUrl(value:string){try{return ['https:','http:'].includes(new URL(value).protocol);}catch{return false;}}
</script>
<style scoped>
.fact-review { margin-top:24px; border-top:1px solid var(--line); padding-top:24px; }
.fact-option { margin-top:20px; min-width:0; }
.fact-option h4 { margin:0 0 12px; font-size:1rem; }
.fact-row { border:1px solid var(--line); border-radius:10px; padding:20px; margin:12px 0; overflow-wrap:anywhere; }
.fact-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; flex-wrap:wrap; }
.fact-heading strong { flex:1; min-width:150px; }
.fact-row .choice-option { margin-top:16px; align-items:flex-start; }
.sources { font-size:.8125rem; padding-left:20px; }
.research-again { margin-top:16px; }
textarea { min-height:80px; width:100%; }
@media(max-width:600px){.fact-row{padding:16px;} .research-again button{width:100%;}}
</style>
