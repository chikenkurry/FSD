<template>
  <section class="option-editor">
    <h3>Options to compare</h3>
    <p>Add the choices and facts members will compare. Use the same criterion name in each option and its question.</p>
    <label>Currency<select v-model="model.currency"><option>SGD</option><option>USD</option><option>EUR</option><option>GBP</option></select></label>
    <article v-for="(option, index) in model.decisionOptions" :key="index">
      <label>Option name<input v-model="option.title" required /></label>
      <button v-if="!option.id" type="button" @click="model.decisionOptions?.splice(index,1)">Remove option</button>
      <div v-for="(fact, fi) in option.facts" :key="fi" class="fact-row">
        <label>Criterion<input v-model="fact.criterion" placeholder="environment or max_cost" required /></label>
        <label>Type<select v-model="fact.valueType"><option value="category">Category</option><option value="number">Number</option><option value="decimal">Exact amount</option><option value="boolean">Yes/no</option><option value="tag_set">Tags</option></select></label>
        <label>Value<select v-if="fact.valueType === 'boolean'" v-model="fact.value"><option value="true">Yes</option><option value="false">No</option></select><input v-else v-model="fact.value" placeholder="For tags, separate with commas" required /></label>
        <label>Unit<input v-model="fact.unit" placeholder="kg, hours, SGD" /></label>
        <label>Source<input v-model="fact.source" placeholder="Specification or quote" required /></label>
        <button type="button" @click="option.facts.splice(fi,1)">Remove fact</button>
      </div>
      <button type="button" @click="option.facts.push({criterion:'',value:'',valueType:'category',unit:'',source:''})">Add fact</button>
    </article>
    <button v-if="(model.decisionOptions?.length || 0) < 8" type="button" @click="model.decisionOptions?.push({title:'',facts:[]})">Add option</button>
    <p>Costs use criterion <strong>max_cost</strong>, type <strong>Exact amount</strong>, and the selected currency as the unit. Costs are per person for the whole decision.</p>
  </section>
</template>
<script setup lang="ts">
import type { Form } from '@/types/form';
const model = defineModel<Form>({ required: true });
</script>
<style scoped>
article { padding: 1rem; margin: 1rem 0; border: 1px solid #cbd5e0; background: #fff; border-radius: 8px; }
.fact-row { display: flex; gap: .5rem; flex-wrap: wrap; align-items: center; }.fact-row label { flex: 1 1 8rem; }
button { padding: .5rem; margin: .3rem; }
</style>
