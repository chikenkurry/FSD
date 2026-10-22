<template>
  <section class="fact-review" aria-labelledby="facts-heading">
    <h3 id="facts-heading">Check the comparison facts</h3>
    <p class="helper-text">These values determine the result. Correct anything inaccurate, check the source, then confirm each fact. Research suggestions require your review.</p>
    <p v-if="!questions.length" class="helper-text">Context-only questions do not need comparison facts.</p>
    <article v-for="option in options" :key="option.id || option.title" class="fact-option">
      <h4>{{ option.title }}</h4>
      <div v-for="q in questions" :key="q.criterion" class="fact-row" :data-testid="`fact-${option.title}-${q.criterion}`">
        <div class="fact-heading"><strong>{{ q.title }}</strong><span class="badge">{{ status(option,q) }}</span></div>
        <fieldset v-if="q.type === 'Multiple choice'"><legend>Comparison values</legend>
          <label v-for="choice in q.options.filter(c=>c.trim())" :key="choice" class="choice-option"><input type="checkbox" :checked="tagValues(fact(option,q)?.value || '').includes(choice)" @change="toggle(option,q,choice,($event.target as HTMLInputElement).checked)" />{{ choice }}</label>
          <button type="button" class="btn-quiet btn-small" @click="edit(option,q,'[]')">None of these apply</button>
        </fieldset>
        <label v-else>Comparison value
          <select v-if="q.type === 'Boolean'" :value="fact(option,q)?.value || ''" @change="edit(option,q,($event.target as HTMLSelectElement).value)"><option value="">Unknown</option><option value="true">Yes</option><option value="false">No</option></select>
          <select v-else-if="q.type === 'Single choice' || q.type === 'Location' || q.type === 'Budget'" :value="fact(option,q)?.value || ''" @change="edit(option,q,($event.target as HTMLSelectElement).value)"><option value="">Unknown</option><option v-for="choice in q.options.filter(c=>c.trim())" :key="choice">{{ choice }}</option></select>
          <input v-else :value="fact(option,q)?.value || ''" :inputmode="q.type === 'Number' ? 'decimal' : 'text'" placeholder="Enter a verified value" @input="edit(option,q,($event.target as HTMLInputElement).value)" />
        </label>
        <p v-if="fact(option,q)?.context?.stale" class="helper-text">The option or question changed. Research or correct this value before confirming it again.</p>
        <p v-if="fact(option,q)?.context?.reason" class="helper-text">Research note: {{ fact(option,q)?.context?.reason }}</p>
        <ul v-if="fact(option,q)?.context?.sources?.length" class="sources"><li v-for="source in fact(option,q)?.context?.sources" :key="source.url"><a v-if="safeUrl(source.url)" :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.title || source.url }}</a></li></ul>
        <label>Source or verification note <span class="optional">(optional)</span><input :value="fact(option,q)?.source || ''" placeholder="Website, menu, or details you checked" @input="source(option,q,($event.target as HTMLInputElement).value)" /></label>
        <label class="choice-option"><input type="checkbox" :checked="factStatus(fact(option,q)) === 'confirmed'" :disabled="!validFact(fact(option,q),q)" @change="approve(option,q,($event.target as HTMLInputElement).checked)" />I checked this value and confirm it can be used.</label>
        <p v-if="q.role === 'hard'" class="helper-text">This is a requirement: verify it with the provider or a reliable source, especially for dietary needs.</p>
        <details class="research-again"><summary>Research or correct this comparison</summary>
          <label>What should research check? <span class="optional">(optional)</span><textarea :value="notes[key(option,q)] || ''" maxlength="1000" placeholder="e.g. Check the current menu; the previous price seems outdated." @input="notes[key(option,q)]=($event.target as HTMLTextAreaElement).value"></textarea></label>
          <button type="button" :disabled="researching" @click="emit('research',option,q,notes[key(option,q)] || '')">{{ researching ? 'Researching…' : 'Research again' }}</button>
          <p class="helper-text">The current value stays available until replacement research finishes. Review any replacement before using it.</p>
        </details>
      </div>
    </article>
  </section>
</template>
<script setup lang="ts">
import { reactive } from 'vue';
import type { DecisionOption, Fact, Form, Question } from '@/types/form';
import { comparisonSignature, factStatus, factType, tagValues, validFact } from '@/services/comparisonFacts';
const props=defineProps<{ form:Form; options:DecisionOption[]; questions:Question[]; researching:boolean }>();
const emit=defineEmits<{(event:'research',option:DecisionOption,question:Question,note:string):void}>();
const notes=reactive<Record<string,string>>({});
const key=(o:DecisionOption,q:Question)=>`${o.id || o.title}:${q.criterion}`;
const fact=(o:DecisionOption,q:Question)=>o.facts.find(f=>f.criterion===q.criterion);
function ensure(o:DecisionOption,q:Question):Fact { let row=fact(o,q); if(!row){ row={criterion:q.criterion!,value:'',valueType:factType(q),unit:q.unit || '',source:'',status:'unknown'}; o.facts.push(row); } return row; }
function edit(o:DecisionOption,q:Question,value:string){ const row=ensure(o,q);row.value=value;row.valueType=factType(q);row.unit=q.criterion==='max_cost' ? props.form.currency || 'SGD' : q.unit || '';row.status='estimated';row.context={...row.context,stale:false,corrected:true,reviewed:false,input_signature:comparisonSignature(props.form,o,q)}; }
function source(o:DecisionOption,q:Question,value:string){const row=ensure(o,q);row.source=value;row.status='estimated';row.context={...row.context,reviewed:false};}
function toggle(o:DecisionOption,q:Question,choice:string,checked:boolean){const values=tagValues(fact(o,q)?.value || '').filter(v=>q.options.includes(v)&&v!==choice);if(checked)values.push(choice);edit(o,q,JSON.stringify(values));}
function approve(o:DecisionOption,q:Question,checked:boolean){const row=ensure(o,q);row.status=checked ? 'confirmed':'estimated';row.context={...row.context,reviewed:checked,input_signature:comparisonSignature(props.form,o,q)};}
function status(o:DecisionOption,q:Question){ const row=fact(o,q); return row?.context?.stale ? 'Needs updating' : factStatus(row)==='confirmed' ? 'Confirmed' : row?.value ? 'Needs review' : 'Missing'; }
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
