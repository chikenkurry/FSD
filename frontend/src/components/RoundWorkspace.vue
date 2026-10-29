<template>
  <main class="workspace" id="main-content" tabindex="-1" :aria-busy="busy">
    <Transition name="reveal"
      ><p v-if="error" role="alert" class="error">{{ error }}</p></Transition
    >
    <div v-if="busy && !snapshot" role="status" class="loading">
      <p class="sr-only">Loading your plan…</p>
      <div class="skeleton title" aria-hidden="true"></div>
      <div class="skeleton tall" aria-hidden="true"></div>
      <div class="skeleton" aria-hidden="true"></div>
    </div>
    <FormParticipantView
      v-if="snapshot && plan && memberCollecting"
      guided
      :round-id="roundId"
      :snapshot="snapshot"
      :title="plan.title"
      :description="plan.description"
      :deadline="deadline"
      @refresh="refresh"
    />
    <template v-else-if="snapshot && plan">
      <header class="round-header page-heading">
        <div>
          <div class="round-meta">
            <Transition name="swap" mode="out-in"
              ><span :key="displayState" :class="['badge', displayState.toLowerCase()]">{{
                stateLabel(displayState)
              }}</span></Transition
            ><span>{{ organiser ? 'You’re organising' : 'You’re a member' }}</span
            ><span aria-hidden="true">·</span><span>Costs in {{ snapshot.currency }}</span
            ><template v-if="roundList.length > 1"
              ><span aria-hidden="true">·</span
              ><span>Round {{ currentRoundNumber }} of {{ roundList.length }}</span></template
            ><template v-if="deadline && plan.state === 'COLLECTING' && !historical"
              ><span aria-hidden="true">·</span
              ><span :class="{ overdue: deadlinePassed }">{{
                deadlinePassed ? 'Deadline passed' : `Answers due ${formatWhen(deadline)}`
              }}</span></template
            ><button
              v-if="!historical && snapshot.previous_round_id"
              type="button"
              class="btn-quiet btn-small round-switch"
              @click="emit('open-round', snapshot.previous_round_id)"
            >
              View earlier round
            </button>
          </div>
          <h1>{{ plan.title }}</h1>
          <p v-if="snapshot.decision_question && snapshot.decision_question !== plan.title" class="decision-question">
            {{ snapshot.decision_question }}
          </p>
          <p v-if="plan.description" class="plan-description">{{ plan.description }}</p>
        </div>
        <button :disabled="busy" @click="refresh" :class="['refresh', { spinning: busy }]">
          <UiIcon name="refresh" />{{ busy ? 'Refreshing…' : 'Refresh status' }}
        </button>
      </header>
      <ol class="round-progress" aria-label="Decision progress" :style="{ '--phase': phase }">
        <li
          v-for="(label, index) in ['Collect responses', 'Review options', 'Confirm choice']"
          :key="label"
          :class="{ current: index === phase, complete: index < phase }"
          :aria-current="index === phase ? 'step' : undefined"
        >
          <span class="phase-dot"
            ><Transition name="swap" mode="out-in"
              ><UiIcon v-if="index < phase" name="check" /><span v-else>{{ index + 1 }}</span></Transition
            ></span
          ><span class="phase-label">{{ label }}</span>
        </li>
      </ol>

      <div :class="['round-body', { 'has-aside': showAside }]">
        <div class="round-main">
          <Transition name="reveal"
            ><p v-if="!organiser && plan.state === 'REVIEWING' && !run" class="callout waiting">
              Collection has closed. The organiser is reviewing the options. Refresh status to check for the result.
            </p></Transition
          >
          <p v-if="backgroundError" role="status" class="helper-text">
            {{ backgroundError }} <button class="btn-small" @click="refresh">Retry status</button>
          </p>
          <div v-if="historical" class="callout historical-callout">
            <p>You’re viewing an earlier round. Its result is preserved; RSVPs for it are read-only.</p>
            <button
              v-if="latestRoundId && latestRoundId !== roundId"
              type="button"
              class="btn-small"
              @click="openLatestRound"
            >
              Open latest round<UiIcon name="arrow" />
            </button>
          </div>

          <Transition name="settle">
            <section v-if="selection" class="selection-panel" aria-labelledby="selection-heading">
              <div class="selection-head">
                <span class="seal" aria-hidden="true"
                  ><svg viewBox="0 0 24 24"><path d="m6 12.5 4 4L18 8" /></svg
                ></span>
                <div>
                  <h2 id="selection-heading">Confirmed selection</h2>
                  <p class="selected-title">{{ selectedTitle }}</p>
                </div>
              </div>
              <p v-if="eventWhen" class="event-when">{{ eventWhen }}</p>
              <p v-if="selectedSummary" class="selected-summary">{{ selectedSummary }}</p>
              <p class="selection-lede">The choice is confirmed. Let your group know whether you’ll be joining.</p>
              <dl v-if="rsvpSummary && rsvpSummary.total > 0" class="rsvp-summary" aria-label="Group attendance">
                <div>
                  <dt>Going</dt>
                  <dd>{{ rsvpSummary.going }}</dd>
                </div>
                <div>
                  <dt>Maybe</dt>
                  <dd>{{ rsvpSummary.maybe }}</dd>
                </div>
                <div>
                  <dt>Not joining</dt>
                  <dd>{{ rsvpSummary.declined }}</dd>
                </div>
              </dl>
              <p
                v-if="organiser && !historical && rsvpSummary && rsvpSummary.declined > 0"
                class="callout warning rsvp-decline-note"
              >
                {{ rsvpSummary.declined === 1 ? '1 member can’t join' : `${rsvpSummary.declined} members can’t join` }}
                this confirmed choice. Revise in a new round if the group needs to choose another option.
              </p>
              <fieldset class="rsvp" :disabled="busy || historical">
                <legend>Your RSVP</legend>
                <div class="choice-list rsvp-options">
                  <label v-for="o in rsvpOptions" :key="o.value" class="choice-option"
                    ><input type="radio" name="rsvp" :value="o.value" v-model="rsvpStatus" />{{ o.label }}</label
                  >
                </div>
                <div class="rsvp-actions">
                  <button
                    class="btn-primary"
                    :disabled="busy || !rsvpStatus || rsvpStatus === savedRsvp"
                    @click="saveRsvp"
                  >
                    {{ savedRsvp ? 'Update RSVP' : 'Save RSVP' }}
                  </button>
                  <button type="button" @click="downloadCalendar"><UiIcon name="document" />Calendar (.ics)</button>
                  <Transition name="reveal"
                    ><p v-if="notice" role="status" class="saved-note">
                      <UiIcon name="check" />{{ notice }}
                    </p></Transition
                  >
                </div>
              </fieldset>
              <p class="helper-text">Selection version {{ selection.selection_version }}</p>
            </section>
          </Transition>

          <section v-if="!candidates.length" class="options-section" aria-labelledby="options-heading">
            <h2 id="options-heading">
              Options being considered <span class="count">{{ snapshot.options.length }}</span>
            </h2>
            <OptionCards
              :options="snapshot.options"
              :currency="snapshot.currency"
              :round-id="roundId"
              :chosen="selection?.candidate_id"
              compact
            />
          </section>

          <div v-if="plan.state === 'COLLECTING' && !historical" ref="ownResponseBox" class="own-response">
            <h2 class="own-heading">Your response</h2>
            <FormParticipantView :round-id="roundId" :snapshot="snapshot" @saved="updateProgress" />
          </div>

          <Transition name="reveal">
            <section class="recommendation-section" v-if="run" aria-labelledby="recommendation-heading">
              <div class="section-heading">
                <div>
                  <h2 id="recommendation-heading">Group recommendation</h2>
                  <p>Options ranked against the group’s confirmed responses.</p>
                </div>
                <span :class="['badge', run.status.toLowerCase()]">{{ stateLabel(run.status) }}</span>
              </div>
              <div v-if="run.status === 'pending'" class="pending" role="status">
                <span class="pulse" aria-hidden="true"></span>Interpreting responses, checking any missing evidence and
                calculating the recommendation. You can return later; progress is saved.
              </div>
              <p v-if="run.recommendation_view.next_action && nextAction" class="callout warning">{{ nextAction }}</p>
              <p v-if="run.recommendation_view.not_counted_members" class="callout">
                {{
                  run.recommendation_view.not_counted_members === 1
                    ? '1 member hadn’t responded when collection closed, so they weren’t counted.'
                    : `${run.recommendation_view.not_counted_members} members hadn’t responded when collection closed, so they weren’t counted.`
                }}
                They can still see the result and RSVP.
              </p>
              <ul v-if="run.issues.length" class="issue-list">
                <li v-for="(issue, index) in run.issues" :key="index">{{ stateLabel(issue.code) }}</li>
              </ul>

              <!-- Result board: the ranking arrives row by row, like a departures display. -->
              <div
                v-if="candidates.length"
                :key="`board-${podiumKey}`"
                class="result-board"
                aria-label="Ranked options"
              >
                <div class="board-head">
                  <p class="board-headline">
                    {{ selection ? 'Confirmed' : 'Top pick' }}:
                    <strong>{{ selection ? selectedTitle : candidates[0]?.title }}</strong>
                  </p>
                  <div class="board-tools">
                    <span>{{ candidates.length }} {{ candidates.length === 1 ? 'option' : 'options' }} ranked</span>
                  </div>
                </div>
                <div class="board-cols" aria-hidden="true">
                  <span>Rank</span><span>Option</span><span>{{ hasPreferences ? 'Average fit' : 'Requirements' }}</span
                  ><span>{{ hasPreferences ? 'Lowest member' : 'Cost' }}</span>
                </div>
                <ol class="board-rows">
                  <li
                    v-for="(candidate, index) in candidates"
                    :key="candidate.candidate_id"
                    :class="{
                      lead: index === 0 && !selection,
                      chosen: selection?.candidate_id === candidate.candidate_id,
                    }"
                    :style="{ '--i': index }"
                  >
                    <button type="button" class="board-row" @click="focusCandidate(candidate.candidate_id)">
                      <span class="board-rank">{{ candidate.rank }}</span>
                      <span class="board-option">
                        <span class="board-thumb" aria-hidden="true"
                          ><img
                            v-if="optionLeadPhoto(candidate.candidate_id)"
                            :src="optionLeadPhoto(candidate.candidate_id)"
                            alt=""
                          /><span v-else>{{ optionMonogram(candidate.title) }}</span></span
                        >
                        <span class="board-name"
                          ><strong>{{ candidate.title }}</strong
                          ><small v-if="optionMeta(candidate.candidate_id)">{{
                            optionMeta(candidate.candidate_id)
                          }}</small></span
                        >
                      </span>
                      <span class="board-fit">
                        <template v-if="hasPreferences"
                          ><span class="board-bar"
                            ><span :style="{ '--v': candidate.average_member_score }"></span></span
                          ><b>{{ percent(candidate.average_member_score) }}</b></template
                        >
                        <span v-else class="met"><UiIcon name="check" />All met</span>
                      </span>
                      <span class="board-min">{{
                        hasPreferences
                          ? percent(candidate.minimum_member_score)
                          : candidate.estimated_cost_minor != null
                            ? money(candidate)
                            : '—'
                      }}</span>
                    </button>
                  </li>
                </ol>
              </div>

              <section v-if="datePoll" class="date-poll-result" aria-labelledby="dates-heading">
                <div class="date-poll-head">
                  <h3 id="dates-heading">When works best</h3>
                  <p>
                    {{ datePoll.respondents }} {{ datePoll.respondents === 1 ? 'answer' : 'answers' }} counted<template
                      v-if="datePoll.best_date"
                    >
                      · Best: <strong>{{ longDate(datePoll.best_date) }}</strong></template
                    >
                  </p>
                </div>
                <ul class="date-rows">
                  <li
                    v-for="(row, di) in datePoll.dates"
                    :key="row.date"
                    :class="{ best: row.date === datePoll.best_date, chosen: row.date === eventDate }"
                    :style="{ '--i': di }"
                  >
                    <span class="date-label"
                      >{{ longDate(row.date) }}<span v-if="row.date === eventDate" class="date-tag">Chosen</span
                      ><span v-else-if="row.date === datePoll.best_date" class="date-tag">Best</span></span
                    >
                    <span class="date-bar" aria-hidden="true">
                      <span class="works" :style="{ '--w': share(row.works) }"></span
                      ><span class="maybe" :style="{ '--w': share(row.maybe) }"></span
                      ><span class="cannot" :style="{ '--w': share(row.cannot) }"></span>
                    </span>
                    <span class="date-counts"
                      >{{ row.works }} works · {{ row.maybe }} if needed · {{ row.cannot }} can’t</span
                    >
                  </li>
                </ul>
              </section>

              <details v-if="run.supplemented_facts?.length" class="supplemented-facts">
                <summary>Evidence added during calculation</summary>
                <p class="helper-text">
                  These sourced details supplemented the published options for this result. They are saved with the
                  calculation.
                </p>
                <div
                  v-for="fact in run.supplemented_facts"
                  :key="`${fact.option_id}:${fact.attribute_id}`"
                  class="supplement"
                >
                  <p>
                    <strong
                      >{{ snapshot.options.find((o) => o.option_id === fact.option_id)?.title }} ·
                      {{ factLabel(fact.attribute_id) }}</strong
                    >: {{ Array.isArray(fact.value) ? fact.value.join(', ') : fact.value }} {{ fact.unit || '' }}
                  </p>
                  <p class="helper-text">{{ fact.source_text }}</p>
                  <ul>
                    <li v-for="source in fact.sources" :key="source.url">
                      <a v-if="safeSource(source.url)" :href="source.url" target="_blank" rel="noopener noreferrer">{{
                        source.title || source.url
                      }}</a>
                    </li>
                  </ul>
                </div>
              </details>

              <h3 v-if="candidates.length" class="detail-heading">Why each option ranked where it did</h3>
              <div class="candidate-grid">
                <article
                  v-for="(candidate, index) in candidates"
                  :key="candidate.candidate_id"
                  :id="`candidate-${candidate.candidate_id}`"
                  :class="[
                    'candidate-card',
                    'rise',
                    {
                      recommended: candidate.rank === 1,
                      chosen: selection?.candidate_id === candidate.candidate_id,
                      spotlighted: focusedCandidateId === candidate.candidate_id,
                      'has-attributes': candidateAttributes(candidate).length > 0,
                    },
                  ]"
                  :style="{ '--i': index }"
                >
                  <div class="candidate-overview">
                    <div v-if="optionPhotos(candidate.candidate_id).length" class="candidate-photo-strip">
                      <figure
                        v-for="(photo, pi) in optionPhotos(candidate.candidate_id)"
                        :key="photo.name"
                        :class="{ lead: pi === 0 }"
                      >
                        <img
                          v-if="photoUrls[photo.name]"
                          :src="photoUrls[photo.name]"
                          :alt="pi === 0 ? candidate.title : ''"
                          loading="lazy"
                          @load="loadedPhotos.add(photo.name)"
                          :class="{ ready: loadedPhotos.has(photo.name) }"
                        />
                        <span v-else class="photo-placeholder" aria-hidden="true"></span>
                        <figcaption v-if="photo.attributions.length && pi === 0">
                          Photo:
                          <template v-for="(a, ai) in photo.attributions" :key="ai"
                            ><a v-if="a.uri" :href="a.uri" target="_blank" rel="noopener noreferrer">{{ a.name }}</a
                            ><span v-else>{{ a.name }}</span></template
                          >
                        </figcaption>
                      </figure>
                    </div>

                    <div class="candidate-body">
                      <p class="rank">
                        <span class="rank-num">{{ candidate.rank }}</span
                        >{{
                          selection?.candidate_id === candidate.candidate_id
                            ? 'Confirmed'
                            : candidate.rank === 1
                              ? 'Recommended'
                              : `Ranked ${ordinal(candidate.rank)}`
                        }}<template v-if="optionKindLabel(candidate.candidate_id)">
                          · {{ optionKindLabel(candidate.candidate_id) }}</template
                        >
                      </p>
                      <h3>
                        <span class="sr-only">{{ candidate.rank === 1 ? 'Recommended: ' : '' }}</span
                        >{{ candidate.title }}
                      </h3>
                      <p v-if="optionMeta(candidate.candidate_id)" class="candidate-meta">
                        {{ optionMeta(candidate.candidate_id) }}
                      </p>
                      <p v-if="optionAddress(candidate.candidate_id)" class="candidate-meta address">
                        {{ optionAddress(candidate.candidate_id) }}
                      </p>
                      <p v-if="optionSummary(candidate.candidate_id)" class="candidate-description">
                        {{ optionSummary(candidate.candidate_id) }}
                      </p>
                      <ul v-if="optionHighlights(candidate.candidate_id).length" class="candidate-highlights">
                        <li v-for="h in optionHighlights(candidate.candidate_id)" :key="h">{{ h }}</li>
                      </ul>

                      <p v-if="candidate.primary_objective_tie_size > 1" class="tie">
                        Equally suitable with {{ candidate.primary_objective_tie_size - 1 }} other
                        {{ candidate.primary_objective_tie_size === 2 ? 'option' : 'options' }}. Cost, time, then ID set
                        the display order.
                      </p>
                      <dl v-if="hasPreferences" class="scores">
                        <div>
                          <dt>Average group fit</dt>
                          <dd>{{ percent(candidate.average_member_score) }}</dd>
                          <span class="meter" aria-hidden="true"
                            ><span :style="{ '--value': candidate.average_member_score }"></span
                          ></span>
                        </div>
                        <div>
                          <dt>Least-satisfied member</dt>
                          <dd>{{ percent(candidate.minimum_member_score) }}</dd>
                          <span class="meter" aria-hidden="true"
                            ><span :style="{ '--value': candidate.minimum_member_score }"></span
                          ></span>
                        </div>
                      </dl>
                      <p v-else class="no-pref-note">Meets the requirements. No scored preferences were collected.</p>

                      <dl class="facts" v-if="candidate.estimated_cost_minor != null || candidate.start_at">
                        <div v-if="candidate.estimated_cost_minor != null">
                          <dt>Cost per person</dt>
                          <dd>{{ money(candidate) }}</dd>
                        </div>
                        <div v-if="candidate.start_at">
                          <dt>When</dt>
                          <dd>
                            {{ new Date(candidate.start_at).toLocaleString()
                            }}<template v-if="candidate.end_at">
                              – {{ new Date(candidate.end_at).toLocaleString() }}</template
                            >
                          </dd>
                        </div>
                      </dl>
                      <p v-if="paretoIds.has(candidate.candidate_id)" class="tradeoff">
                        Trade-off: {{ tradeoffs(candidate.candidate_id) }}
                      </p>
                      <button
                        :class="{ 'btn-primary': candidate.rank === 1 }"
                        v-if="
                          organiser && !selection && plan.state === 'REVIEWING' && confirming !== candidate.candidate_id
                        "
                        :disabled="busy"
                        @click="datePoll ? startConfirm(candidate) : confirm(candidate)"
                      >
                        Confirm {{ candidate.title }}<UiIcon name="check" />
                      </button>
                      <Transition name="reveal">
                        <form
                          v-if="confirming === candidate.candidate_id"
                          class="confirm-when"
                          @submit.prevent="confirm(candidate)"
                        >
                          <p class="confirm-when-title">When is {{ candidate.title }}?</p>
                          <div class="confirm-when-fields">
                            <label
                              >Date<select v-model="confirmDate" required>
                                <option v-for="row in datePoll!.dates" :key="row.date" :value="row.date">
                                  {{ longDate(row.date) }} · {{ row.works }} works{{
                                    row.date === datePoll!.best_date ? ' (best)' : ''
                                  }}
                                </option>
                              </select></label
                            >
                            <label
                              >Start time <span class="optional">(optional)</span
                              ><input v-model="confirmTime" type="time"
                            /></label>
                          </div>
                          <p class="helper-text">Members are asked to RSVP and can add it to their calendar.</p>
                          <div class="confirm-when-actions">
                            <button class="btn-primary" :disabled="busy || !confirmDate">
                              Confirm for {{ confirmDate ? longDate(confirmDate) : 'this date'
                              }}<UiIcon name="check" /></button
                            ><button type="button" class="btn-quiet" @click="confirming = ''">Cancel</button>
                          </div>
                        </form>
                      </Transition>
                    </div>
                  </div>

                  <div v-if="candidateAttributes(candidate).length" class="attr-breakdown">
                    <div class="attr-breakdown-head">
                      <h4>Scoring by criterion</h4>
                      <span
                        >{{ candidateAttributes(candidate).length }}
                        {{ candidateAttributes(candidate).length === 1 ? 'criterion' : 'criteria' }}</span
                      >
                    </div>
                    <ul class="attr-list">
                      <li
                        v-for="(attr, ai) in candidateAttributes(candidate)"
                        :key="attr.attribute_id"
                        class="attr-item"
                        :style="{ '--ai': ai }"
                      >
                        <div class="attr-top">
                          <strong class="attr-name">{{ factLabel(attr.attribute_id) }}</strong>
                          <span v-if="attr.score != null" :class="['attr-score', attrFitClass(attr.score)]">{{
                            attr.role === 'hard'
                              ? attr.score >= 1
                                ? 'Passed'
                                : 'Not met'
                              : `${Math.round(attr.score * 100)}% fit`
                          }}</span>
                        </div>
                        <p class="attr-role">
                          {{
                            attr.role === 'hard'
                              ? 'Requirement'
                              : attr.weight != null
                                ? `Preference · ${Math.round(attr.weight * 100)}% weight`
                                : 'Option detail'
                          }}<template v-if="attr.supplemented"> · Researched</template>
                        </p>
                        <p class="attr-value">
                          <template v-if="attr.attribute_id === 'option_rating'">Members’ direct ratings</template>
                          <template v-else-if="Array.isArray(attr.value) && attr.value.length">{{
                            attr.value.join(', ')
                          }}</template>
                          <template v-else-if="attr.value != null && String(attr.value) !== ''">{{
                            formatAttrValue(attr)
                          }}</template>
                          <span v-else class="muted">Not specified</span>
                        </p>
                        <span v-if="attr.score != null" class="meter attr-meter" aria-hidden="true"
                          ><span :class="attrFitClass(attr.score)" :style="{ '--value': attr.score }"></span
                        ></span>
                        <p class="attr-reason">{{ attr.reason }}</p>
                      </li>
                    </ul>
                  </div>
                </article>
              </div>
              <div v-if="run.recommendation_view.unavailable_candidates.length" class="unavailable">
                <h3>Ruled out</h3>
                <ul>
                  <li v-for="candidate in run.recommendation_view.unavailable_candidates" :key="candidate.candidate_id">
                    <span>{{ candidate.title }}</span
                    ><span class="muted">{{ unavailableReason(candidate) }}</span>
                  </li>
                </ul>
              </div>
            </section>
          </Transition>
        </div>

        <aside v-if="showAside" class="round-aside">
          <Transition name="reveal" mode="out-in">
            <section
              class="panel organiser-panel"
              v-if="['COLLECTING', 'REVIEWING'].includes(plan.state)"
              :key="plan.state"
              aria-labelledby="organiser-heading"
            >
              <h2 id="organiser-heading">Organiser controls</h2>
              <p class="aside-lede">
                {{
                  plan.state === 'COLLECTING'
                    ? 'Share the invitation, then close collection once every member has submitted.'
                    : 'Collection is closed. Calculate the recommendation to compare eligible options.'
                }}
              </p>
              <div v-if="plan.state === 'COLLECTING'" class="collect-progress">
                <template v-if="readiness">
                  <div class="collect-figure">
                    <strong
                      >{{ readiness.submitted }}<span class="of">/{{ readiness.members }}</span></strong
                    ><span>{{ readiness.members === 1 ? 'member has' : 'members have' }} submitted</span>
                  </div>
                  <span class="meter" aria-hidden="true"
                    ><span
                      :style="{ '--value': readiness.members ? readiness.submitted / readiness.members : 0 }"
                    ></span
                  ></span>
                  <p class="helper-text">Closing collection freezes the roster and submitted responses.</p>
                </template>
                <p v-else-if="progressError" class="helper-text">{{ progressError }}</p>
              </div>
              <div v-if="plan.state === 'COLLECTING'" class="deadline-field">
                <div class="deadline-head">
                  <span class="field-label">Response deadline</span>
                  <button v-if="!editingDeadline" type="button" class="btn-quiet btn-small" @click="startDeadlineEdit">
                    {{ deadline ? 'Change' : 'Set a deadline' }}
                  </button>
                </div>
                <p v-if="!editingDeadline" :class="['deadline-value', { overdue: deadlinePassed }]">
                  {{
                    deadline
                      ? `${formatWhen(deadline)} · ${deadlinePassed ? 'passed' : relative(deadline)}`
                      : 'None. Members can answer until you close collection.'
                  }}
                </p>
                <form v-else class="deadline-edit" @submit.prevent="saveDeadline">
                  <label class="sr-only" for="deadline-input">Collect answers until</label>
                  <input id="deadline-input" v-model="deadlineDraft" type="datetime-local" :min="nowLocal()" required />
                  <div class="deadline-actions">
                    <button class="btn-primary btn-small" :disabled="busy || !deadlineDraft">Save</button
                    ><button
                      v-if="deadline"
                      type="button"
                      class="btn-quiet btn-small"
                      :disabled="busy"
                      @click="clearDeadline"
                    >
                      Remove</button
                    ><button type="button" class="btn-quiet btn-small" @click="editingDeadline = false">Cancel</button>
                  </div>
                </form>
              </div>
              <Transition name="reveal">
                <div v-if="shareUrl && plan.state === 'COLLECTING'" class="invitation-field">
                  <label for="invite-link">Invitation link</label>
                  <input
                    id="invite-link"
                    readonly
                    :value="shareUrl"
                    @focus="($event.target as HTMLInputElement).select()"
                  />
                  <button :class="['copy-button', { 'btn-primary': !copied }]" @click="copyInvite">
                    <Transition name="swap" mode="out-in"
                      ><span :key="String(copied)" class="copy-label"
                        ><UiIcon :name="copied ? 'check' : 'link'" />{{ copied ? 'Copied' : 'Copy invitation' }}</span
                      ></Transition
                    >
                  </button>
                  <p class="helper-text">
                    Anyone with this link can join and respond. Share it with the people involved in this decision.
                  </p>
                </div>
              </Transition>
              <div class="aside-actions">
                <button
                  class="btn-primary"
                  v-if="plan.state === 'COLLECTING' && !shareUrl"
                  :disabled="busy"
                  @click="makeInvite"
                >
                  <UiIcon name="people" />Create invitation link
                </button>
                <button type="button" v-if="plan.state === 'COLLECTING' && ownIncomplete" @click="scrollToOwnResponse">
                  Answer your response
                </button>
                <button
                  v-if="plan.state === 'COLLECTING' && waitingOn.length"
                  type="button"
                  :disabled="busy"
                  @click="remind"
                >
                  <UiIcon :name="reminded ? 'check' : 'people'" />{{
                    reminded
                      ? 'Reminder copied'
                      : `Remind ${waitingOn.length === 1 ? waitingOn[0] : `${waitingOn.length} people`}`
                  }}
                </button>
                <button
                  v-if="plan.state === 'COLLECTING' && !readiness?.can_close && readiness?.can_close_early"
                  type="button"
                  :disabled="busy"
                  @click="closeEarly"
                >
                  Close with {{ readiness.submitted }} of {{ readiness.members }} responses
                </button>
                <button v-if="plan.state === 'COLLECTING'" :disabled="busy || !readiness?.can_close" @click="close">
                  Close collection
                </button>
                <button
                  class="btn-primary"
                  v-if="plan.state === 'REVIEWING'"
                  :disabled="busy || run?.status === 'pending'"
                  @click="recommend"
                >
                  {{
                    calculating || run?.status === 'pending'
                      ? 'Calculating…'
                      : run?.status === 'failed'
                        ? 'Retry recommendation'
                        : run
                          ? 'Recalculate'
                          : 'Calculate recommendation'
                  }}<UiIcon v-if="!calculating && run?.status !== 'pending'" name="arrow" />
                </button>
              </div>
              <div v-if="plan.state === 'COLLECTING' && readiness && !readiness.can_close" class="waiting-list">
                <p>Collection stays open until every member has submitted a complete, current response.</p>
                <ul class="incomplete-list">
                  <li
                    v-for="(member, index) in readiness.members_status.filter((m) => m.status !== 'complete')"
                    :key="member.id || index"
                  >
                    <span
                      ><strong
                        >{{ member.name }}<template v-if="member.user_id === auth.userID"> (you)</template></strong
                      >{{
                        member.status === 'stale' ? 'Needs to review the current form' : 'Awaiting complete submission'
                      }}</span
                    ><button
                      v-if="member.id && member.role !== 'ORGANISER' && member.user_id !== auth.userID"
                      type="button"
                      class="btn-quiet btn-danger btn-small"
                      :disabled="busy"
                      @click="removeRosterMember(member)"
                    >
                      Remove
                    </button>
                  </li>
                </ul>
              </div>
            </section>
          </Transition>
          <section
            v-if="plan.state === 'REVIEWING' && candidates.length && !selection"
            class="panel recheck-panel"
            aria-labelledby="recheck-heading"
          >
            <h2 id="recheck-heading">Still accurate?</h2>
            <p class="aside-lede">
              Before you confirm, check the top {{ Math.min(3, candidates.length) }} options against current sources{{
                planDates ? ` for ${planDates}` : ''
              }}: prices, details and whether they’re open.
            </p>
            <button type="button" :disabled="recheck.state === 'loading'" @click="recheckFacts">
              <UiIcon name="refresh" :class="{ spinning: recheck.state === 'loading' }" />{{
                recheck.state === 'loading'
                  ? 'Checking sources…'
                  : recheck.state === 'done'
                    ? 'Check again'
                    : 'Check top options'
              }}
            </button>
            <p v-if="recheck.message" class="helper-text" role="status">{{ recheck.message }}</p>
            <Transition name="reveal">
              <div v-if="recheck.state === 'done'" class="recheck-results">
                <p class="recheck-summary">{{ recheckSummary }}</p>
                <ul>
                  <li
                    v-for="row in recheck.rows"
                    :key="`${row.option}:${row.criterion}`"
                    :class="['recheck-row', row.status]"
                  >
                    <div class="recheck-top">
                      <strong>{{ row.title }}</strong
                      ><span class="recheck-status">{{ recheckStatusLabels[row.status] }}</span>
                    </div>
                    <p>
                      {{ factLabel(row.criterion) }}:
                      <template v-if="row.status === 'changed'"
                        ><s>{{ row.before }}</s> → </template
                      >{{ row.status === 'unconfirmed' ? row.before || 'No current source' : row.after }}
                    </p>
                    <a v-if="row.source" :href="row.source.url" target="_blank" rel="noopener noreferrer">{{
                      row.source.title || 'Source'
                    }}</a>
                  </li>
                </ul>
                <p class="helper-text">
                  This check is advisory. It doesn’t change the ranking. If something important changed, revise in a new
                  round.
                </p>
              </div>
            </Transition>
          </section>
          <section v-if="['REVIEWING', 'CONFIRMED'].includes(plan.state)" class="panel revise-panel">
            <h2>Need to change the decision?</h2>
            <p>
              Revise the options, facts or questions in a new round. This round and any confirmed choice remain in the
              history. Members review their answers again.
            </p>
            <button :disabled="busy" @click="reopen">Revise in a new round</button>
          </section>
        </aside>
      </div>
    </template>
  </main>
</template>
<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue';
import UiIcon from './UiIcon.vue';
import FormParticipantView from './FormParticipantView.vue';
import OptionCards from './OptionCards.vue';
import { apiService, ApiError, request } from '@/services/api';
import { checkpointKey, readCheckpoint, writeCheckpoint } from '@/services/checkpoints';
import { operationId } from '@/services/ids';
import { factLabel, factValue } from '@/services/facts';
import { useAuthStore } from '@/stores/auth';
import type {
  Snapshot,
  PlanRow,
  Round,
  Run,
  Selection,
  Candidate,
  ReadinessMember,
  RsvpSummary,
  Overview,
  AttributeBreakdownItem,
  PublishedFact,
} from '@/types/form';
const props = defineProps<{ roundId: string; inviteToken?: string }>();
const emit = defineEmits<{ (event: 'open-round', id: string): void; (event: 'open-draft', id: string): void }>();
const auth = useAuthStore();
const snapshot = ref<Snapshot>();
const plan = ref<PlanRow>();
const roundList = ref<Round[]>([]);
const run = ref<Run>();
const selection = ref<Selection>();
const busy = ref(false);
const error = ref('');
const inviteCheckpointKey = computed(() => checkpointKey(auth.userID, `invite:${props.roundId}`));
const shareUrl = ref(readCheckpoint<string>(inviteCheckpointKey.value) || '');
const copied = ref(false);
const notice = ref('');
const calculating = ref(false);
const readiness = ref<{
  submitted: number;
  members: number;
  can_close: boolean;
  can_close_early: boolean;
  members_status: ReadinessMember[];
}>();
const progressError = ref('');
const backgroundError = ref('');
const historical = ref(false);
let pollTimer: ReturnType<typeof setTimeout> | undefined;
let polling = false;
const rsvpStatus = ref('');
const savedRsvp = ref('');
const rsvpRevision = ref(0);
const rsvpSummary = ref<RsvpSummary>();
let alive = true;
const ownResponseBox = ref<HTMLElement>();
const podiumKey = ref(0);
const confirming = ref('');
const confirmDate = ref('');
const confirmTime = ref('');
const datePoll = computed(() => (run.value?.date_poll?.dates.length ? run.value.date_poll : undefined));
const eventDate = computed(() => selection.value?.selected_details?.event_date || '');
const eventWhen = computed(() => {
  const d = eventDate.value;
  if (!d) return '';
  const t = selection.value?.selected_details?.event_time;
  return t
    ? new Date(`${d}T${t}`).toLocaleString(undefined, {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        hour: 'numeric',
        minute: '2-digit',
      })
    : new Date(`${d}T00:00:00Z`).toLocaleDateString(undefined, {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        timeZone: 'UTC',
      });
});
function longDate(day: string) {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  });
}
function share(count: number) {
  return datePoll.value?.respondents ? count / datePoll.value.respondents : 0;
}
function startConfirm(candidate: Candidate) {
  confirming.value = candidate.candidate_id;
  confirmDate.value = datePoll.value?.best_date || datePoll.value?.dates[0]?.date || '';
  confirmTime.value = '';
}
const editingDeadline = ref(false);
const deadlineDraft = ref('');
const reminded = ref(false);
type RecheckRow = {
  option: string;
  title: string;
  criterion: string;
  before: string;
  after: string;
  status: 'same' | 'changed' | 'unconfirmed' | 'new';
  source?: { url: string; title?: string };
};
const recheckStatusLabels: Record<string, string> = {
  same: 'Unchanged',
  changed: 'Changed',
  unconfirmed: 'Couldn’t confirm',
  new: 'Found',
};
const recheck = reactive<{ state: 'idle' | 'loading' | 'done' | 'failed'; rows: RecheckRow[]; message: string }>({
  state: 'idle',
  rows: [],
  message: '',
});
const focusedCandidateId = ref('');
const liveOverviews = reactive<Record<string, Overview>>({});
const photoUrls = reactive<Record<string, string>>({});
const loadedPhotos = reactive(new Set<string>());

const rsvpOptions = [
  { value: 'GOING', label: 'Going' },
  { value: 'MAYBE', label: 'Maybe' },
  { value: 'DECLINED', label: 'Not joining' },
];
const organiser = computed(() => plan.value?.created_by_user_id === auth.userID);
const displayState = computed(() =>
  historical.value ? (selection.value ? 'CONFIRMED' : 'REVIEWING') : plan.value?.state || '',
);
// Members answer in a focused, page-by-page flow; organisers keep the full workspace.
const showAside = computed(
  () =>
    organiser.value && !historical.value && ['COLLECTING', 'REVIEWING', 'CONFIRMED'].includes(plan.value?.state || ''),
);
const memberCollecting = computed(() => !organiser.value && !historical.value && plan.value?.state === 'COLLECTING');
const hasPreferences = computed(() =>
  snapshot.value?.questions.some((question) => question.role === 'soft' || !question.role),
);
const candidates = computed(() =>
  run.value?.recommendation_view.recommendation
    ? [run.value.recommendation_view.recommendation, ...run.value.recommendation_view.alternatives]
    : [],
);
const paretoIds = computed(
  () => new Set(run.value?.recommendation_view.pareto_alternatives.map((row) => row.candidate_id)),
);
const selectedOption = computed(() =>
  snapshot.value?.options.find((row) => row.option_id === selection.value?.candidate_id),
);
const selectedTitle = computed(
  () =>
    candidates.value.find((row) => row.candidate_id === selection.value?.candidate_id)?.title ||
    selectedOption.value?.title ||
    'Selection confirmed',
);
const selectedSummary = computed(() => selectedOption.value?.brief?.summary || selectedOption.value?.description || '');
const ownIncomplete = computed(
  () => !!readiness.value?.members_status.some((m) => m.user_id === auth.userID && m.status !== 'complete'),
);
const currentRoundNumber = computed(() => roundList.value.find((r) => r.id === props.roundId)?.round_number || 1);
const deadline = computed(() => roundList.value.find((r) => r.id === props.roundId)?.deadline_at || null);
const now = ref(Date.now());
let clock: ReturnType<typeof setInterval> | undefined;
const deadlinePassed = computed(() => !!deadline.value && Date.parse(deadline.value) <= now.value);
const waitingOn = computed(() =>
  (readiness.value?.members_status || [])
    .filter((m) => m.status !== 'complete' && m.user_id !== auth.userID)
    .map((m) => m.name),
);
const planDates = computed(() => {
  const a = plan.value?.time_window_start,
    b = plan.value?.time_window_end;
  if (!a) return '';
  const f = (v: string) =>
    new Date(v).toLocaleDateString(undefined, { day: 'numeric', month: 'short', timeZone: 'UTC' });
  return b && f(a) !== f(b) ? `${f(a)} – ${f(b)}` : f(a);
});
const recheckSummary = computed(() => {
  const changed = recheck.rows.filter((r) => r.status === 'changed').length,
    unknown = recheck.rows.filter((r) => r.status === 'unconfirmed').length;
  return changed
    ? `${changed} ${changed === 1 ? 'detail has' : 'details have'} changed since you published.`
    : unknown
      ? `Nothing changed, but ${unknown} ${unknown === 1 ? 'detail' : 'details'} couldn’t be confirmed.`
      : 'Everything checked still matches what you published.';
});
const latestRoundId = computed(() => [...roundList.value].sort((a, b) => b.round_number - a.round_number)[0]?.id || '');

// Fetch live Google Places metadata & photos for options that carry a place_id.
watch(
  () => snapshot.value?.options,
  async (options) => {
    if (!options?.length || !props.roundId) return;
    await Promise.all(
      options.map(async (opt) => {
        const placeId = opt.identity?.place_id;
        if (!placeId || liveOverviews[opt.option_id]) return;
        try {
          const card = await apiService.placeCard(props.roundId, placeId);
          if (!alive) return;
          liveOverviews[opt.option_id] = card;
          for (const photo of (card.photos || []).slice(0, 2)) {
            if (photoUrls[photo.name]) continue;
            const response = await fetch(apiService.placePhotoUrl(props.roundId, photo.name), {
              headers: { Authorization: `Bearer ${sessionStorage.getItem('session_token') || ''}` },
            });
            if (response.ok && alive) photoUrls[photo.name] = URL.createObjectURL(await response.blob());
          }
        } catch {
          /* Fall back to stored brief and monogram banner */
        }
      }),
    );
  },
  { immediate: true },
);

function optionOf(id: string) {
  return snapshot.value?.options.find((o) => o.option_id === id);
}
function optionPhotos(id: string) {
  return (liveOverviews[id]?.photos || []).slice(0, 2);
}
function optionLeadPhoto(id: string) {
  const first = optionPhotos(id)[0];
  return first ? photoUrls[first.name] || '' : '';
}
function optionKindLabel(id: string) {
  const kind = optionOf(id)?.identity?.kind || 'other';
  return (
    (
      { place: 'Place', destination: 'Destination', event: 'Event', activity: 'Activity', other: '' } as Record<
        string,
        string
      >
    )[kind] || ''
  );
}
function optionSummary(id: string) {
  const opt = optionOf(id);
  const live = liveOverviews[id];
  return opt?.brief?.summary || live?.summary || opt?.description || live?.review_summary || '';
}
function optionHighlights(id: string) {
  const opt = optionOf(id);
  const live = liveOverviews[id];
  return (opt?.brief?.highlights?.length ? opt.brief.highlights : live?.highlights || []).slice(0, 4);
}
function optionMeta(id: string) {
  const opt = optionOf(id);
  const live = liveOverviews[id];
  const parts: string[] = [];
  if (live?.rating)
    parts.push(`${live.rating.toFixed(1)} ★${live.rating_count ? ` (${live.rating_count.toLocaleString()})` : ''}`);
  if (live?.price_level != null) parts.push(live.price_level === 0 ? 'Free' : '$'.repeat(live.price_level));
  if (live?.kind_label) parts.push(live.kind_label);
  const note = opt?.brief?.price_note || live?.price_note;
  if (note) parts.push(note);
  const when = opt?.brief?.when || live?.when;
  if (when) parts.push(when);
  return parts.join(' · ');
}
function optionAddress(id: string) {
  const opt = optionOf(id);
  const live = liveOverviews[id];
  return live?.address || opt?.brief?.where || live?.where || '';
}
function optionMonogram(title: string) {
  const words = title.trim().split(/\s+/).filter(Boolean);
  return (
    words
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase() || '')
      .join('') || '?'
  );
}
function focusCandidate(id: string) {
  focusedCandidateId.value = id;
  document.getElementById(`candidate-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  setTimeout(() => {
    if (focusedCandidateId.value === id) focusedCandidateId.value = '';
  }, 1600);
}
function attrFitClass(score?: number | null) {
  if (score == null) return 'fit-neutral';
  return score >= 0.75 ? 'fit-high' : score >= 0.45 ? 'fit-mid' : 'fit-low';
}
function formatAttrValue(attr: AttributeBreakdownItem) {
  return factValue(
    { criterion: attr.attribute_id, value: attr.value, value_type: attr.value_type, unit: attr.unit },
    snapshot.value?.currency || 'SGD',
  );
}
function candidateAttributes(candidate: Candidate): AttributeBreakdownItem[] {
  const fromRun = run.value?.attribute_breakdown?.[candidate.candidate_id];
  if (fromRun?.length) return fromRun;
  const opt = optionOf(candidate.candidate_id);
  const questions = (snapshot.value?.questions || []).filter((q) => q.role !== 'informational');
  const activeQuestions = questions.filter((q) => q.criterion && q.criterion !== 'preferences');
  const suppFacts = (run.value?.supplemented_facts || []).filter((f) => f.option_id === candidate.candidate_id);
  const optFacts = opt?.facts || [];
  const merged = new Map<string, AttributeBreakdownItem>();
  const softCount = Math.max(1, activeQuestions.filter((q) => (q.role || 'soft') === 'soft').length);

  for (const q of activeQuestions) {
    const cid = q.criterion!;
    const supp = suppFacts.find((f) => f.attribute_id === cid);
    const local = optFacts.find((f) => f.criterion === cid);
    const value = supp ? supp.value : local?.value;
    const status = supp ? 'confirmed' : local?.status || 'unknown';
    if (value == null && status !== 'confirmed') continue;
    const isHard = q.role === 'hard';
    const score = isHard ? 1 : candidate.average_member_score;
    merged.set(cid, {
      attribute_id: cid,
      role: isHard ? 'hard' : 'soft',
      value,
      value_type: supp?.value_type || local?.value_type || q.mapping?.value_type || 'category',
      unit: supp?.unit ?? local?.unit ?? q.mapping?.unit ?? null,
      status,
      weight: isHard ? null : 1 / softCount,
      score,
      reason: isHard
        ? 'Meets group requirement'
        : score >= 0.75
          ? 'Strong alignment with group preferences'
          : score >= 0.45
            ? 'Partial alignment with group preferences'
            : 'Lower alignment with group preferences',
      supplemented: Boolean(supp),
    });
  }
  for (const supp of suppFacts) {
    if (merged.has(supp.attribute_id)) continue;
    merged.set(supp.attribute_id, {
      attribute_id: supp.attribute_id,
      role: hasPreferences.value ? 'soft' : 'context',
      value: supp.value,
      value_type: supp.value_type,
      unit: supp.unit,
      status: 'confirmed',
      weight: null,
      score: hasPreferences.value ? candidate.average_member_score : null,
      reason: hasPreferences.value ? 'Evaluated against group preferences' : 'Verified option attribute',
      supplemented: true,
    });
  }
  for (const local of optFacts) {
    if (merged.has(local.criterion) || local.value == null || local.value === '') continue;
    merged.set(local.criterion, {
      attribute_id: local.criterion,
      role: 'context',
      value: local.value,
      value_type: local.value_type || 'category',
      unit: local.unit,
      status: local.status || 'confirmed',
      weight: null,
      score: null,
      reason: 'Supporting option detail',
      supplemented: false,
    });
  }
  return [...merged.values()];
}

const actionMessages: Record<string, string> = {
  OPTION_FACTS_REQUIRED:
    'Some option facts remain unresolved after the evidence check. The organiser can correct them or try fresh research by revising in a new round.',
  RESPONSES_OR_CONFIRMATIONS_REQUIRED:
    'Responses or requirement confirmations are incomplete. Review the round before requesting another calculation.',
  REVISE_OPTIONS_OR_REQUIREMENTS:
    'No option meets the group requirements. Revise the choices or requirements in a new round.',
  RECOMMENDATION_IN_PROGRESS: '',
  DECISION_SETUP_REVIEW_REQUIRED: 'The organiser needs to review the decision setup.',
  RECOMMENDATION_RETRY_REQUIRED: 'The calculation failed. The organiser can retry.',
};
const nextAction = computed(() => actionMessages[run.value?.recommendation_view.next_action || ''] ?? '');
function stateLabel(value: string) {
  return value
    .toLowerCase()
    .replaceAll('_', ' ')
    .replace(/^./, (c) => c.toUpperCase());
}
function safeSource(value: string) {
  try {
    return new URL(value).protocol === 'https:';
  } catch {
    return false;
  }
}
function unavailableLabel(status: string) {
  return (
    (
      { INFEASIBLE: 'Doesn’t meet the group’s requirements', UNRESOLVED: 'Needs verified option details' } as Record<
        string,
        string
      >
    )[status.toUpperCase()] || stateLabel(status)
  );
}
function unavailableReason(candidate: { candidate_id: string; status: string }) {
  if (candidate.status.toUpperCase() === 'UNRESOLVED') {
    const missing = (run.value?.fact_requests || [])
      .filter((f) => f.option_id === candidate.candidate_id)
      .map((f) => factLabel(f.attribute_id));
    if (missing.length) return `Needs verified details: ${missing.join(', ')}`;
  }
  return unavailableLabel(candidate.status);
}
function scrollToOwnResponse() {
  ownResponseBox.value?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
function openLatestRound() {
  if (plan.value?.state === 'DRAFT' && organiser.value && snapshot.value) emit('open-draft', snapshot.value.plan_id);
  else if (latestRoundId.value) emit('open-round', latestRoundId.value);
}
function nowLocal() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}
function toLocalInput(iso: string) {
  const d = new Date(iso);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}
function formatWhen(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
  });
}
function relative(iso: string) {
  const minutes = Math.round((Date.parse(iso) - now.value) / 60000);
  if (minutes < 60) return `${Math.max(1, minutes)} min left`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} ${hours === 1 ? 'hour' : 'hours'} left`;
  return `${Math.round(hours / 24)} days left`;
}
function startDeadlineEdit() {
  deadlineDraft.value = deadline.value ? toLocalInput(deadline.value) : '';
  editingDeadline.value = true;
}
async function saveDeadline() {
  await act(async () => {
    await apiService.setDeadline(props.roundId, new Date(deadlineDraft.value).toISOString());
    await refreshRounds();
    editingDeadline.value = false;
  });
}
async function clearDeadline() {
  await act(async () => {
    await apiService.setDeadline(props.roundId, null);
    await refreshRounds();
    editingDeadline.value = false;
  });
}
async function refreshRounds() {
  const rounds = await apiService.rounds(snapshot.value!.plan_id);
  roundList.value = [...rounds.data].sort((a, b) => a.round_number - b.round_number);
}
// Guests have no email on file, so reminders go out through the organiser's own channels.
async function remind() {
  await act(async () => {
    if (!shareUrl.value) await makeInvite();
    const due = deadline.value && !deadlinePassed.value ? ` by ${formatWhen(deadline.value)}` : '';
    const text = `Reminder: we’re deciding “${plan.value!.title}”. Please add your answers${due}. It takes about ${Math.max(1, Math.round(snapshot.value!.questions.length * 0.4))} min and your answers stay private.`;
    if (navigator.share && matchMedia('(pointer: coarse)').matches) {
      try {
        await navigator.share({ title: plan.value!.title, text, url: shareUrl.value });
        return;
      } catch {
        /* fall back to copying */
      }
    }
    await navigator.clipboard.writeText(`${text}\n${shareUrl.value}`);
    reminded.value = true;
    setTimeout(() => {
      reminded.value = false;
    }, 2400);
  });
}
async function closeEarly() {
  const r = readiness.value!;
  const missing = r.members - r.submitted;
  if (
    !window.confirm(
      `Close with ${r.submitted} of ${r.members} responses? ${missing === 1 ? '1 member hasn’t' : `${missing} members haven’t`} submitted. Their answers won’t be counted, but they can still see the result and RSVP.`,
    )
  )
    return;
  await act(async () => {
    await apiService.close(props.roundId, true);
    await load();
  });
}
async function recheckFacts() {
  if (!snapshot.value) return;
  recheck.state = 'loading';
  recheck.message = '';
  recheck.rows = [];
  const top = candidates.value.slice(0, 3);
  const published = new Map<string, PublishedFact>();
  for (const c of top)
    for (const f of optionOf(c.candidate_id)?.facts || [])
      if (f.criterion !== 'option_rating') published.set(`${c.candidate_id}:${f.criterion}`, f);
  const definitions = new Map<string, { criterion: string; value_type: string; unit: string | null }>();
  for (const f of published.values())
    if (!definitions.has(f.criterion) && definitions.size < 7)
      definitions.set(f.criterion, {
        criterion: f.criterion,
        value_type: f.value_type || 'category',
        unit: f.unit || null,
      });
  definitions.set('open_on_plan_dates', { criterion: 'open_on_plan_dates', value_type: 'boolean', unit: null });
  try {
    const result = await apiService.research<{
      facts: {
        option: string;
        criterion: string;
        value: unknown;
        value_type?: string;
        unit?: string | null;
        sources: { url: string; title?: string }[];
      }[];
    }>(props.roundId, 'facts', {
      decision_question: snapshot.value.decision_question,
      currency: snapshot.value.currency,
      options: top.map((c) => ({
        key: c.candidate_id,
        title: c.title,
        source_url: optionOf(c.candidate_id)?.identity?.source_url || '',
      })),
      attributes: [...definitions.values()],
      correction: `Re-check with current sources${planDates.value ? ` for ${planDates.value}` : ''}: current prices and details, and whether each option is open and operating then.`,
    });
    const currency = snapshot.value.currency;
    const show = (f: { criterion: string; value: unknown; value_type?: string; unit?: string | null }) =>
      factValue({ criterion: f.criterion, value: f.value, value_type: f.value_type, unit: f.unit ?? null }, currency);
    const found = new Map(result.facts.map((f) => [`${f.option}:${f.criterion}`, f]));
    const rows: RecheckRow[] = [];
    for (const c of top)
      for (const d of definitions.values()) {
        const before = published.get(`${c.candidate_id}:${d.criterion}`),
          after = found.get(`${c.candidate_id}:${d.criterion}`);
        const base = {
          option: c.candidate_id,
          title: c.title,
          criterion: d.criterion,
          before: before ? show(before) : '',
          after: after ? show(after) : '',
          source: after?.sources?.[0],
        };
        if (!after) {
          if (before || d.criterion === 'open_on_plan_dates') rows.push({ ...base, status: 'unconfirmed' });
          continue;
        }
        if (d.criterion === 'open_on_plan_dates') {
          rows.push({
            ...base,
            status: after.value === false ? 'changed' : 'same',
            before: after.value === false ? 'Open' : '',
            after: after.value === false ? 'May be closed then' : 'Open then',
          });
          continue;
        }
        rows.push({
          ...base,
          status: !before
            ? 'new'
            : base.before.toLocaleLowerCase() === base.after.toLocaleLowerCase()
              ? 'same'
              : 'changed',
        });
      }
    const order = { changed: 0, unconfirmed: 1, new: 2, same: 3 };
    recheck.rows = rows.sort((a, b) => order[a.status] - order[b.status]);
    recheck.state = 'done';
  } catch (e) {
    recheck.state = 'failed';
    recheck.message =
      e instanceof ApiError && e.code === 'FACT_COLLECTOR_NOT_CONFIGURED'
        ? 'Source checks need AI research to be set up on this server.'
        : 'Sources couldn’t be checked right now. Try again in a moment.';
  }
}
function ordinal(n: number) {
  const s = ['th', 'st', 'nd', 'rd'],
    v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]!);
}
const phase = computed(() =>
  selection.value ? 2 : plan.value?.state === 'REVIEWING' ? 1 : plan.value?.state === 'CONFIRMED' ? 2 : 0,
);
function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}
function money(row: Candidate) {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: row.currency || snapshot.value!.currency,
  }).format(row.estimated_cost_minor! / 10 ** (row.currency_minor_digits ?? snapshot.value!.currency_minor_digits));
}
function tradeoffs(id: string) {
  const labels: Record<string, string> = {
    HIGHER_MINIMUM_SATISFACTION: 'higher minimum fit',
    LOWER_MINIMUM_SATISFACTION: 'lower minimum fit',
    HIGHER_AVERAGE_SATISFACTION: 'higher average fit',
    LOWER_AVERAGE_SATISFACTION: 'lower average fit',
    EQUIVALENT_GROUP_METRICS: 'similar group metrics',
  };
  return run.value?.recommendation_view.pareto_alternatives
    .find((row) => row.candidate_id === id)
    ?.tradeoffs?.map((code) => labels[code] || code)
    .join(', ');
}
async function optional<T>(get: () => Promise<T>) {
  try {
    return await get();
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return undefined;
    throw e;
  }
}
async function act(fn: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    await fn();
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Request failed';
  } finally {
    busy.value = false;
  }
}
async function load() {
  snapshot.value = await apiService.snapshot(props.roundId);
  plan.value = await apiService.plan(snapshot.value.plan_id);
  const rounds = await apiService.rounds(snapshot.value.plan_id);
  roundList.value = [...rounds.data].sort((a, b) => a.round_number - b.round_number);
  historical.value = [...rounds.data].sort((a, b) => b.round_number - a.round_number)[0]?.id !== props.roundId;
  run.value = await optional(() => apiService.result(props.roundId));
  selection.value = await optional(() => apiService.selection(props.roundId));
  if (selection.value) {
    const own = await apiService.rsvp(props.roundId);
    rsvpRevision.value = own.revision;
    rsvpStatus.value = savedRsvp.value = own.status || '';
    rsvpSummary.value = own.summary;
  }
  await updateProgress();
}
async function refresh() {
  await act(load);
}
async function updateProgress() {
  if (!organiser.value || plan.value?.state !== 'COLLECTING') {
    readiness.value = undefined;
    return;
  }
  try {
    const row = await request<{
      member_count: number;
      complete_count: number;
      can_close: boolean;
      can_close_early?: boolean;
      members: ReadinessMember[];
      progress: { submittedCount?: number };
    }>(`/api/planning/v1/rounds/${props.roundId}/readiness`);
    readiness.value = {
      submitted: row.complete_count,
      members: row.member_count,
      can_close: row.can_close,
      can_close_early: !!row.can_close_early,
      members_status: row.members,
    };
    progressError.value = '';
  } catch {
    readiness.value = undefined;
    progressError.value = 'Progress could not be loaded. Refresh before closing.';
  }
}
async function removeRosterMember(member: ReadinessMember) {
  if (!member.id || !window.confirm(`Remove ${member.name} from this plan?`)) return;
  await act(async () => {
    await apiService.removeMember(member.id!);
    await updateProgress();
  });
}
async function makeInvite() {
  await act(async () => {
    const invite = await apiService.invite(snapshot.value!.plan_id, auth.userID);
    shareUrl.value = `${location.origin}/#${new URLSearchParams({ round: props.roundId, invite: invite.token })}`;
    writeCheckpoint(inviteCheckpointKey.value, shareUrl.value);
  });
}
async function copyInvite() {
  await act(async () => {
    await navigator.clipboard.writeText(shareUrl.value);
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 2400);
  });
}
async function close() {
  const count = readiness.value
    ? ` ${readiness.value.submitted} of ${readiness.value.members} members have submitted.`
    : '';
  if (
    !window.confirm(`Close collection?${count} This freezes the roster and responses; members can’t edit afterwards.`)
  )
    return;
  await act(async () => {
    await apiService.close(props.roundId);
    await load();
  });
}
async function recommend() {
  calculating.value = true;
  await act(async () => {
    run.value = await apiService.recommend(props.roundId);
    podiumKey.value++;
  });
  calculating.value = false;
  schedulePoll();
}
async function reopen() {
  if (!window.confirm('Create a new editable round? Existing results and RSVPs stay attached to this round.')) return;
  await act(async () => {
    const key = `reopen:${props.roundId}`;
    const operation = sessionStorage.getItem(key) || operationId();
    sessionStorage.setItem(key, operation);
    await apiService.reopen(props.roundId, operation);
    emit('open-draft', snapshot.value!.plan_id);
  });
}
function schedulePoll() {
  clearTimeout(pollTimer);
  if (alive && !selection.value) pollTimer = setTimeout(pollStatus, run.value?.status === 'pending' ? 1000 : 5000);
}
async function pollStatus() {
  if (!alive) return;
  if (document.hidden || busy.value || polling) {
    schedulePoll();
    return;
  }
  polling = true;
  try {
    const current = await apiService.plan(snapshot.value!.plan_id);
    if (!alive) return;
    const previousState = plan.value?.state;
    plan.value = current;
    if (current.state !== previousState) {
      const rounds = await apiService.rounds(snapshot.value!.plan_id);
      if (alive) {
        roundList.value = [...rounds.data].sort((a, b) => a.round_number - b.round_number);
        historical.value = [...rounds.data].sort((a, b) => b.round_number - a.round_number)[0]?.id !== props.roundId;
      }
    }
    if (current.state === 'COLLECTING' && !historical.value) {
      await updateProgress();
      backgroundError.value = '';
      return;
    }
    const previousRunStatus = run.value?.status;
    const latestRun = await optional(() => apiService.result(props.roundId));
    if (!alive) return;
    if (latestRun?.status === 'ranked' && previousRunStatus !== 'ranked') podiumKey.value++;
    run.value = latestRun;
    const chosen = await optional(() => apiService.selection(props.roundId));
    if (!alive) return;
    if (chosen) {
      const first = !selection.value;
      selection.value = chosen;
      const own = await apiService.rsvp(props.roundId);
      if (!alive) return;
      rsvpSummary.value = own.summary;
      if (first) {
        rsvpRevision.value = own.revision;
        rsvpStatus.value = savedRsvp.value = own.status || '';
      }
    }
    await updateProgress();
    backgroundError.value = '';
  } catch {
    if (alive)
      backgroundError.value =
        'Status could not be updated. Your saved response and background calculation are retained; updates will retry.';
  } finally {
    polling = false;
    schedulePoll();
  }
}
function visible() {
  if (!document.hidden && alive && snapshot.value) {
    clearTimeout(pollTimer);
    void pollStatus();
  }
}
async function confirm(candidate: Candidate) {
  // With a date poll the inline date form is the confirmation step.
  const when =
    datePoll.value && confirming.value === candidate.candidate_id
      ? { date: confirmDate.value, time: confirmTime.value || undefined }
      : undefined;
  if (!when && !window.confirm(`Confirm “${candidate.title}” as the group’s choice? Members will be asked to RSVP.`))
    return;
  await act(async () => {
    const key = `confirmation:${props.roundId}:${run.value!.run_id}:${candidate.candidate_id}:${when?.date || ''}:${when?.time || ''}`;
    const operation = sessionStorage.getItem(key) || operationId();
    sessionStorage.setItem(key, operation);
    selection.value = await apiService.confirm(
      props.roundId,
      run.value!.run_id,
      candidate.candidate_id,
      operation,
      when,
    );
    confirming.value = '';
    await load();
  });
}
async function saveRsvp() {
  notice.value = '';
  await act(async () => {
    await apiService.saveRsvp(props.roundId, selection.value!.selection_version, rsvpRevision.value, rsvpStatus.value);
    const own = await apiService.rsvp(props.roundId);
    rsvpRevision.value = own.revision;
    savedRsvp.value = own.status || rsvpStatus.value;
    rsvpSummary.value = own.summary;
    notice.value = 'RSVP saved.';
  });
}
function downloadCalendar() {
  if (!plan.value || !selection.value) return;
  const candidate = candidates.value.find((c) => c.candidate_id === selection.value?.candidate_id);
  const stamp = (d: Date) =>
    d
      .toISOString()
      .replace(/[-:]/g, '')
      .replace(/\.\d{3}/, '');
  const now = new Date();
  // Prefer the date the organiser confirmed, then the option's own time, then the plan's first day.
  const chosen = selection.value.selected_details?.event_date || '';
  const chosenTime = selection.value.selected_details?.event_time || '';
  const planDay = plan.value.time_window_start?.slice(0, 10) || '';
  const allDay = (chosen && !chosenTime) || (!chosen && !candidate?.start_at && !!planDay);
  const day = chosen || planDay;
  const start =
    chosen && chosenTime
      ? new Date(`${chosen}T${chosenTime}`)
      : candidate?.start_at
        ? new Date(candidate.start_at)
        : new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 19, 0, 0);
  const end =
    chosen && chosenTime
      ? new Date(start.getTime() + 7200000)
      : candidate?.end_at
        ? new Date(candidate.end_at)
        : new Date(start.getTime() + 7200000);
  const compact = (d: string) => d.replaceAll('-', '');
  const next = (d: string) => {
    const n = new Date(`${d}T00:00:00Z`);
    n.setUTCDate(n.getUTCDate() + 1);
    return n.toISOString().slice(0, 10);
  };
  const clean = (v?: string) => (v || '').replace(/\r?\n/g, '\\n').replace(/[,;]/g, '\\$&');
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//What2Do//Confirmed Plan//EN',
    'BEGIN:VEVENT',
    `UID:${props.roundId}-v${selection.value.selection_version}@what2do`,
    `DTSTAMP:${stamp(now)}`,
    ...(allDay
      ? [`DTSTART;VALUE=DATE:${compact(day)}`, `DTEND;VALUE=DATE:${compact(next(day))}`]
      : [`DTSTART:${stamp(start)}`, `DTEND:${stamp(end)}`]),
    `SUMMARY:${clean(`${plan.value.title}: ${selectedTitle.value}`)}`,
    ...(selectedSummary.value ? [`DESCRIPTION:${clean(selectedSummary.value)}`] : []),
    ...(selectedOption.value?.brief?.where ? [`LOCATION:${clean(selectedOption.value.brief.where)}`] : []),
    'END:VEVENT',
    'END:VCALENDAR',
  ];
  const blob = new Blob([lines.join('\r\n')], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${plan.value.title.toLowerCase().replace(/[^a-z0-9]+/g, '-') || 'plan'}.ics`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
onMounted(async () => {
  await act(async () => {
    if (props.inviteToken) {
      try {
        await apiService.snapshot(props.roundId);
      } catch (e) {
        if (e instanceof ApiError && (e.status === 403 || e.status === 404))
          await apiService.join(props.inviteToken, auth.userID, auth.username);
        else throw e;
      }
    }
    await load();
    if (props.inviteToken) history.replaceState(null, '', `/#${new URLSearchParams({ round: props.roundId })}`);
  });
  if (!alive) return;
  if (snapshot.value) schedulePoll();
  document.addEventListener('visibilitychange', visible);
});
onMounted(() => {
  clock = setInterval(() => {
    now.value = Date.now();
  }, 30000);
});
onUnmounted(() => {
  clearInterval(clock);
  alive = false;
  clearTimeout(pollTimer);
  document.removeEventListener('visibilitychange', visible);
  Object.values(photoUrls).forEach((url) => URL.revokeObjectURL(url));
});
</script>
<style scoped>
.workspace {
  padding: clamp(28px, 5vh, 56px) var(--gutter) 80px;
}
.loading .title {
  height: 56px;
  width: 40%;
}
.loading .tall {
  height: 180px;
}
.round-header {
  margin-bottom: 28px;
}
.round-header h1 {
  overflow-wrap: anywhere;
  font-size: clamp(2.125rem, 1.5rem + 1.8vw, 3.25rem);
  color: var(--night);
  margin-bottom: 10px;
}
.round-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--muted);
  font-size: 0.875rem;
  margin-bottom: 14px;
}
.decision-question {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--ink-2);
  margin: 0 0 8px;
  overflow-wrap: anywhere;
}
.plan-description {
  font-size: 1rem;
  color: var(--muted);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.refresh {
  flex-shrink: 0;
}
.refresh.spinning .ui-icon {
  animation: spin 900ms linear infinite;
}

/* Progress: three stops on one line. */
.round-progress {
  position: relative;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  list-style: none;
  padding: 0;
  margin: 0 0 36px;
}
.round-progress::before,
.round-progress::after {
  content: '';
  position: absolute;
  top: 16px;
  left: 17px;
  width: calc(100% * 2 / 3);
  height: 3px;
  border-radius: 3px;
  background: var(--sky-100);
}
.round-progress::after {
  width: calc(100% * 2 / 3 * var(--phase) / 2);
  background: var(--blue);
  transition: width 700ms var(--ease-out);
}
.round-progress li {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 0;
  color: var(--muted);
  font-size: 0.9375rem;
  font-weight: 600;
  transition: color var(--base) ease-out;
}
.phase-label {
  padding: 0 14px 0 12px;
  background: var(--ground);
}
.phase-dot {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 2px solid var(--sky-200);
  background: var(--ground);
  font-size: 0.875rem;
  flex-shrink: 0;
  transition:
    background-color var(--base) ease-out,
    border-color var(--base) ease-out,
    color var(--base) ease-out;
}
.round-progress .current {
  color: var(--blue-ink);
}
.current .phase-dot {
  background: var(--blue);
  color: #fff;
  border-color: var(--blue);
}
.complete {
  color: var(--ink);
}
.complete .phase-dot {
  color: var(--blue);
  background: var(--surface);
  border-color: var(--blue);
}
.phase-dot .ui-icon {
  width: 16px;
  height: 16px;
}

.round-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: clamp(24px, 3vw, 48px);
  align-items: start;
}
.round-body.has-aside {
  grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
}
.round-main {
  min-width: 0;
}
.round-aside {
  position: sticky;
  top: 24px;
  display: grid;
  gap: 16px;
  min-width: 0;
}
.round-aside .panel {
  margin: 0;
  padding: 24px;
}
.round-aside h2 {
  font-size: 1.25rem;
  margin-bottom: 6px;
}
.aside-lede,
.revise-panel p {
  color: var(--muted);
  font-size: 0.9375rem;
}
.collect-progress {
  margin: 20px 0 8px;
}
.collect-figure {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.collect-figure strong {
  font-size: 3rem;
  line-height: 1;
  font-weight: 300;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
  color: var(--night);
}
.collect-figure .of {
  font-size: 1.5rem;
  color: var(--faint);
}
.collect-figure > span {
  color: var(--muted);
  font-size: 0.9375rem;
}
.invitation-field {
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
}
.invitation-field > label {
  margin: 0 0 8px;
}
.invitation-field input {
  font-size: 0.875rem;
  min-height: 44px;
}
.copy-button {
  width: 100%;
  margin-top: 10px;
}
.copy-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.aside-actions {
  display: grid;
  gap: 10px;
  margin-top: 20px;
}
.aside-actions button {
  width: 100%;
}
.overdue {
  color: var(--danger);
  font-weight: 600;
}
.deadline-field {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}
.deadline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.field-label {
  font-size: 0.9375rem;
  font-weight: 600;
}
.deadline-value {
  margin: 4px 0 0;
  font-size: 0.9375rem;
  color: var(--ink-2);
}
.deadline-edit {
  display: grid;
  gap: 10px;
  margin-top: 8px;
}
.deadline-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.recheck-panel button .spinning {
  animation: spin 900ms linear infinite;
}
.recheck-results {
  margin-top: 16px;
}
.recheck-summary {
  font-weight: 600;
  font-size: 0.9375rem;
}
.recheck-results ul {
  list-style: none;
  margin: 0 0 12px;
  padding: 0;
}
.recheck-row {
  padding: 10px 0;
  border-top: 1px solid var(--line);
  font-size: 0.875rem;
}
.recheck-row p {
  margin: 2px 0;
  color: var(--ink-2);
  overflow-wrap: anywhere;
}
.recheck-row a {
  font-size: 0.8125rem;
}
.recheck-top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.recheck-status {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--muted);
  white-space: nowrap;
}
.recheck-row.changed .recheck-status {
  color: var(--warn);
}
.recheck-row.unconfirmed .recheck-status {
  color: var(--muted);
}
.recheck-row.same .recheck-status {
  color: var(--ok);
}
.waiting-list {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
  font-size: 0.9375rem;
}
.waiting-list > p {
  color: var(--muted);
  font-size: 0.875rem;
}
.incomplete-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.incomplete-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-top: 1px solid var(--line);
}
.incomplete-list li > span {
  display: grid;
  font-size: 0.875rem;
  color: var(--muted);
  min-width: 0;
  overflow-wrap: anywhere;
}
.incomplete-list strong {
  color: var(--ink);
  font-size: 0.9375rem;
}

.waiting {
  margin: 0 0 24px;
}
.historical-callout {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 24px;
}
.historical-callout p {
  margin: 0;
}
.options-section {
  margin: 0 0 40px;
}
.options-section h2,
.own-heading,
.detail-heading {
  font-size: 1.25rem;
  display: flex;
  gap: 10px;
  align-items: baseline;
  margin-bottom: 16px;
}
.count {
  font-size: 0.9375rem;
  font-weight: 400;
  color: var(--faint);
  font-variant-numeric: tabular-nums;
}
.own-response {
  margin: 0 0 40px;
  scroll-margin-top: 24px;
}
.own-response :deep(.response-flow) {
  margin-top: 0;
}

.recommendation-section {
  margin: 0 0 40px;
}
.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
}
.section-heading h2 {
  font-size: 1.5rem;
  margin-bottom: 4px;
}
.section-heading p {
  color: var(--muted);
  margin: 0;
}
.pending {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  margin-bottom: 20px;
  border-radius: 12px;
  background: var(--surface);
  border: 1px solid var(--line);
  color: var(--ink-2);
  font-size: 0.9375rem;
}
.pulse {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--blue);
  flex-shrink: 0;
  animation: pulse 1.2s ease-in-out infinite;
}
.issue-list {
  font-size: 0.9375rem;
  color: var(--muted);
}

/* Result board */
.result-board {
  border-radius: 20px;
  overflow: hidden;
  background: var(--surface);
  box-shadow: var(--shadow-md);
  margin-bottom: 28px;
  font-variant-numeric: tabular-nums;
}
.board-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 20px 24px;
  background: var(--night);
  color: #fff;
}
.board-headline {
  margin: 0;
  font-size: 1.375rem;
  font-weight: 300;
  overflow-wrap: anywhere;
}
.board-headline strong {
  font-weight: 600;
}
.board-tools {
  display: flex;
  align-items: center;
  gap: 14px;
  color: #b9cdf0;
  font-size: 0.875rem;
}
.board-replay {
  background: transparent;
  border-color: rgba(255, 255, 255, 0.3);
  color: #fff;
}
.board-replay:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  border-color: #fff;
  color: #fff;
}
.board-cols,
.board-row {
  display: grid;
  grid-template-columns: 56px minmax(0, 2fr) minmax(140px, 1.2fr) minmax(90px, 0.6fr);
  align-items: center;
  gap: 16px;
  padding: 0 24px;
}
.board-cols {
  padding-top: 12px;
  padding-bottom: 10px;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--muted);
  background: var(--surface-2);
  border-bottom: 1px solid var(--line);
}
.board-cols > span:last-child,
.board-min {
  text-align: right;
}
.board-rows {
  list-style: none;
  margin: 0;
  padding: 0;
}
.board-rows li {
  border-bottom: 1px solid var(--line);
  animation: row-in 700ms var(--ease-out) both;
  animation-delay: calc(min(var(--i), 8) * 110ms + 150ms);
}
.board-rows li:last-child {
  border-bottom: 0;
}
@keyframes row-in {
  from {
    opacity: 0;
    transform: translateY(16px);
    clip-path: inset(0 0 100% 0);
  }
  to {
    clip-path: inset(0 0 0 0);
  }
}
.board-row {
  width: 100%;
  min-height: 76px;
  border: 0;
  border-radius: 0;
  background: transparent;
  text-align: left;
  font-weight: 400;
  color: var(--ink);
}
.board-row:hover:not(:disabled) {
  background: var(--sky-50);
  color: var(--ink);
}
.board-row:active:not(:disabled) {
  transform: none;
}
.board-rank {
  font-size: 1.75rem;
  font-weight: 300;
  color: var(--muted);
}
.board-option {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}
.board-thumb {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  border-radius: 10px;
  overflow: hidden;
  display: grid;
  place-items: center;
  background: var(--sky-100);
  color: var(--blue-ink);
  font-weight: 700;
  font-size: 0.875rem;
}
.board-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.board-name {
  display: grid;
  min-width: 0;
  line-height: 1.3;
}
.board-name strong {
  font-size: 1.0625rem;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.board-name small {
  font-size: 0.875rem;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.board-fit {
  display: flex;
  align-items: center;
  gap: 12px;
}
.board-fit b {
  width: 4ch;
  text-align: right;
  font-weight: 600;
}
.board-bar {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: var(--sky-100);
  overflow: hidden;
}
.board-bar > span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--blue);
  transform-origin: left;
  transform: scaleX(var(--v));
  animation: bar-in 1200ms var(--ease-out) both;
  animation-delay: calc(min(var(--i), 8) * 110ms + 500ms);
}
@keyframes bar-in {
  from {
    transform: scaleX(0);
  }
}
.met {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ok);
  font-weight: 600;
}
.met .ui-icon {
  width: 18px;
  height: 18px;
}
.board-min {
  font-weight: 600;
  color: var(--ink-2);
}
.board-rows li.lead .board-row,
.board-rows li.chosen .board-row {
  background: var(--blue);
  color: #fff;
}
.board-rows li.lead .board-row:hover:not(:disabled),
.board-rows li.chosen .board-row:hover:not(:disabled) {
  background: var(--blue-hover);
}
:is(.lead, .chosen) .board-rank,
:is(.lead, .chosen) .board-min,
:is(.lead, .chosen) .met {
  color: #fff;
}
:is(.lead, .chosen) .board-name small {
  color: #d4e2fa;
}
:is(.lead, .chosen) .board-bar {
  background: rgba(255, 255, 255, 0.25);
}
:is(.lead, .chosen) .board-bar > span {
  background: #fff;
}
:is(.lead, .chosen) .board-thumb {
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
}

.date-poll-result {
  margin: 0 0 28px;
  padding: 22px 24px;
  border-radius: 20px;
  background: var(--surface);
  border: 1px solid var(--line);
}
.date-poll-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.date-poll-head h3 {
  margin: 0;
}
.date-poll-head p {
  margin: 0;
  color: var(--muted);
  font-size: 0.9375rem;
}
.date-rows {
  list-style: none;
  margin: 0;
  padding: 0;
}
.date-rows li {
  display: grid;
  grid-template-columns: minmax(130px, 180px) minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  padding: 10px 12px;
  border-radius: 12px;
  animation: rise 420ms var(--ease-out) both;
  animation-delay: calc(min(var(--i), 8) * 50ms);
}
.date-rows li.best {
  background: var(--sky-50);
}
.date-rows li.chosen {
  background: var(--sky-100);
}
.date-label {
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}
.date-tag {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--blue-ink);
}
.date-bar {
  display: flex;
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
  background: var(--sky-100);
}
.date-bar > span {
  width: calc(var(--w) * 100%);
  transform-origin: left;
  animation: meter-fill 900ms var(--ease-out) both;
}
.date-bar .works {
  background: #1f9d5c;
}
.date-bar .maybe {
  background: #e2a93b;
}
.date-bar .cannot {
  background: #c4515f;
}
.date-counts {
  font-size: 0.875rem;
  color: var(--muted);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.confirm-when {
  margin-top: 8px;
  padding: 16px;
  border-radius: 14px;
  background: var(--sky-50);
  border: 1px solid var(--line);
}
.confirm-when-title {
  font-weight: 600;
  margin: 0 0 4px;
}
.confirm-when-fields {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: 0 12px;
}
.confirm-when-fields label {
  margin: 10px 0 0;
}
.confirm-when-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
}
.event-when {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--blue-ink);
  margin: 0 0 10px;
}
.supplemented-facts {
  overflow-wrap: anywhere;
  margin: 0 0 28px;
}
.supplement {
  padding: 12px 0;
  border-top: 1px solid var(--line);
}
.detail-heading {
  margin-top: 8px;
}
.candidate-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
  container-type: inline-size;
}
.candidate-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: 20px;
  overflow: hidden;
  overflow-wrap: anywhere;
  scroll-margin-top: 24px;
  transition:
    box-shadow var(--base) var(--ease-out),
    border-color var(--base) var(--ease-out);
}
.candidate-card.has-attributes {
  grid-template-columns: minmax(280px, 380px) minmax(0, 1fr);
}
.candidate-card:not(.has-attributes) .candidate-overview:has(.candidate-photo-strip) {
  display: grid;
  grid-template-columns: minmax(200px, 300px) minmax(0, 1fr);
}
.candidate-card:not(.has-attributes) .candidate-photo-strip {
  height: 100%;
  min-height: 200px;
}
.candidate-card.recommended {
  border-color: var(--sky-300);
}
.candidate-card.chosen {
  border-color: var(--blue);
  box-shadow: 0 0 0 1px var(--blue);
}
.candidate-card.spotlighted {
  box-shadow:
    0 0 0 3px var(--sky-200),
    var(--shadow-md);
  border-color: var(--blue);
}
.candidate-overview {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.candidate-card.has-attributes .candidate-overview {
  border-right: 1px solid var(--line);
}

.candidate-photo-strip {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 2px;
  height: 168px;
  background: var(--sky-100);
}
.candidate-photo-strip:has(figure:only-child) {
  grid-template-columns: 1fr;
}
.candidate-photo-strip figure {
  position: relative;
  margin: 0;
  overflow: hidden;
  background: var(--sky-100);
}
.candidate-photo-strip img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  opacity: 0;
  transform: scale(1.03);
  transition:
    opacity 500ms var(--ease-out),
    transform 900ms var(--ease-out);
}
.candidate-photo-strip img.ready {
  opacity: 1;
  transform: none;
}
.photo-placeholder {
  position: absolute;
  inset: 0;
  background: var(--sky-100);
  animation: pulse 1.6s ease-in-out infinite;
}
.candidate-photo-strip figcaption {
  position: absolute;
  left: 8px;
  bottom: 8px;
  max-width: calc(100% - 16px);
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 0.6875rem;
  color: #fff;
  background: rgba(10, 33, 80, 0.72);
}
.candidate-photo-strip figcaption a {
  color: #fff;
}

.candidate-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  padding: 22px 24px 24px;
  min-width: 0;
}
.rank {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--muted);
  margin: 0 0 6px;
}
.rank-num {
  display: grid;
  place-items: center;
  min-width: 28px;
  height: 28px;
  padding: 0 6px;
  border-radius: 8px;
  background: var(--sky-100);
  color: var(--blue-ink);
  font-variant-numeric: tabular-nums;
}
.recommended .rank {
  color: var(--blue-ink);
}
.recommended .rank-num,
.chosen .rank-num {
  background: var(--blue);
  color: #fff;
}
.candidate-card h3 {
  font-size: 1.375rem;
  margin-bottom: 4px;
}
.candidate-meta {
  font-size: 0.9375rem;
  color: var(--muted);
  margin: 0 0 2px;
  overflow-wrap: anywhere;
}
.candidate-meta.address {
  margin-bottom: 8px;
}
.candidate-description {
  font-size: 0.9375rem;
  color: var(--ink-2);
  margin: 6px 0 10px;
  overflow-wrap: anywhere;
}
.candidate-highlights {
  margin: 0 0 14px;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  font-size: 0.875rem;
  color: var(--ink-2);
}
.candidate-highlights li {
  display: flex;
  align-items: center;
  gap: 8px;
}
.candidate-highlights li::before {
  content: '';
  width: 5px;
  height: 5px;
  border-radius: 1px;
  background: var(--blue);
}
.tie {
  font-size: 0.875rem;
  color: var(--muted);
  margin-bottom: 10px;
}
.no-pref-note {
  font-size: 0.9375rem;
  color: var(--ok);
  margin-bottom: 14px;
}
.scores {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin: 8px 0 16px;
}
.scores > div {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: baseline;
  gap: 6px 8px;
}
.scores dt {
  font-size: 0.8125rem;
  color: var(--muted);
  font-weight: 600;
}
.scores dd {
  margin: 0;
  font-size: 1.375rem;
  font-weight: 300;
  font-variant-numeric: tabular-nums;
  color: var(--night);
}
.scores .meter {
  grid-column: 1 / -1;
}

.attr-breakdown {
  display: flex;
  flex-direction: column;
  padding: 22px 24px;
  min-width: 0;
  background: var(--surface-2);
}
.attr-breakdown-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 14px;
}
.attr-breakdown-head h4 {
  font-size: 1rem;
  margin: 0;
}
.attr-breakdown-head span {
  font-size: 0.875rem;
  color: var(--muted);
}
.attr-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 12px;
  align-content: start;
}
.attr-item {
  display: flex;
  flex-direction: column;
  padding: 14px 16px;
  border-radius: 14px;
  background: var(--surface);
  border: 1px solid var(--line);
  animation: rise var(--slow) var(--ease-out) both;
  animation-delay: calc(min(var(--ai, 0), 6) * 60ms);
}
.attr-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.attr-name {
  font-size: 0.9375rem;
}
.attr-score {
  font-size: 0.875rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.attr-score.fit-high {
  color: var(--ok);
}
.attr-score.fit-mid {
  color: var(--warn);
}
.attr-score.fit-low {
  color: var(--danger);
}
.attr-score.fit-neutral {
  color: var(--muted);
}
.attr-role {
  font-size: 0.8125rem;
  color: var(--muted);
  margin: 2px 0 8px;
}
.attr-value {
  font-size: 0.9375rem;
  font-weight: 600;
  margin: 0 0 10px;
}
.attr-meter {
  height: 5px;
  margin-bottom: 8px;
  margin-top: auto;
}
.attr-meter > span.fit-high {
  background: #1f9d5c;
}
.attr-meter > span.fit-mid {
  background: #d98a00;
}
.attr-meter > span.fit-low {
  background: var(--danger);
}
.attr-reason {
  font-size: 0.8125rem;
  color: var(--muted);
  margin: 0;
}

.facts {
  display: grid;
  gap: 8px;
  margin: 0 0 14px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  font-size: 0.9375rem;
}
.facts > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.facts dt {
  color: var(--muted);
}
.facts dd {
  margin: 0;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.tradeoff {
  font-size: 0.875rem;
  color: var(--muted);
  margin-bottom: 12px;
}
.candidate-body > button {
  margin-top: auto;
  align-self: flex-start;
}
.unavailable {
  margin-top: 28px;
}
.unavailable h3 {
  font-size: 1rem;
  color: var(--ink-2);
  margin-bottom: 10px;
}
.unavailable ul {
  list-style: none;
  padding: 0;
  margin: 0;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--surface);
}
.unavailable li {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 14px 18px;
  font-size: 0.9375rem;
}
.unavailable li + li {
  border-top: 1px solid var(--line);
}
.unavailable li > span:first-child {
  text-decoration: line-through;
  text-decoration-color: var(--faint);
}

.round-switch {
  padding: 2px 10px;
  min-height: 28px;
  font-size: 0.8125rem;
}

/* Confirmed selection */
.selection-panel {
  margin: 0 0 40px;
  padding: clamp(24px, 3vw, 36px);
  border-radius: 20px;
  background: var(--surface);
  border: 1px solid var(--sky-300);
  box-shadow: var(--shadow-md);
}
.selection-head {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 14px;
}
.selection-head h2 {
  font-size: 0.9375rem;
  color: var(--blue-ink);
  margin-bottom: 2px;
  letter-spacing: 0;
}
.seal {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--blue);
  flex-shrink: 0;
  animation: seal-in 520ms var(--ease-out) both;
}
@keyframes seal-in {
  from {
    transform: scale(0.6);
    opacity: 0;
  }
}
.seal svg {
  width: 28px;
  height: 28px;
  fill: none;
  stroke: #fff;
  stroke-width: 2.4;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 20;
  stroke-dashoffset: 0;
  animation: draw 600ms 240ms var(--ease-out) both;
}
@keyframes draw {
  from {
    stroke-dashoffset: 20;
  }
}
.selected-title {
  font-size: clamp(1.75rem, 1.3rem + 1.2vw, 2.5rem);
  font-weight: 300;
  letter-spacing: -0.02em;
  line-height: 1.15;
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--night);
}
.selected-summary {
  font-size: 1rem;
  color: var(--ink-2);
  margin: 0 0 10px;
}
.selection-lede {
  color: var(--muted);
}
.rsvp-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
  margin: 4px 0 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  overflow: hidden;
  width: fit-content;
  max-width: 100%;
}
.rsvp-summary > div {
  padding: 12px 22px;
  display: grid;
}
.rsvp-summary > div + div {
  border-left: 1px solid var(--line);
}
.rsvp-summary dt {
  font-size: 0.8125rem;
  color: var(--muted);
}
.rsvp-summary dd {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 300;
  color: var(--night);
}
.rsvp-decline-note {
  margin: 0 0 16px;
}
.rsvp {
  margin: 20px 0 12px;
}
.rsvp-options {
  grid-template-columns: repeat(3, minmax(0, 200px));
}
.rsvp-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  flex-wrap: wrap;
}
.saved-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
}
.saved-note .ui-icon {
  width: 16px;
  height: 16px;
}
.settle-enter-active {
  transition:
    opacity var(--slow) var(--ease-out),
    transform var(--slow) var(--ease-out);
}
.settle-enter-from {
  opacity: 0;
  transform: translateY(12px) scale(0.99);
}

@media (max-width: 1180px) {
  .round-body.has-aside {
    grid-template-columns: minmax(0, 1fr);
  }
  .round-aside {
    position: static;
    order: -1;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
  }
}
@container (max-width: 760px) {
  .candidate-card.has-attributes,
  .candidate-card:not(.has-attributes) .candidate-overview:has(.candidate-photo-strip) {
    grid-template-columns: minmax(0, 1fr);
  }
  .candidate-card.has-attributes .candidate-overview {
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }
  .candidate-card:not(.has-attributes) .candidate-photo-strip {
    min-height: 0;
    height: 168px;
  }
}
@media (max-width: 760px) {
  .workspace {
    padding: 24px 16px 40px;
  }
  .round-header > button {
    align-self: flex-start;
  }
  .round-progress li {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
    font-size: 0.8125rem;
  }
  .round-progress li {
    gap: 8px;
  }
  .phase-label {
    padding: 0 4px 0 0;
  }
  .board-head {
    padding: 16px 18px;
  }
  .board-cols {
    display: none;
  }
  .board-row {
    grid-template-columns: 28px minmax(0, 1fr) auto;
    grid-template-areas: 'rank opt min' 'rank fit fit';
    gap: 8px 12px;
    padding: 14px 18px;
  }
  .board-rank {
    grid-area: rank;
    font-size: 1.375rem;
  }
  .board-option {
    grid-area: opt;
  }
  .board-fit {
    grid-area: fit;
  }
  .board-min {
    grid-area: min;
    font-size: 0.875rem;
  }
  .board-thumb {
    display: none;
  }
  .candidate-body,
  .attr-breakdown {
    padding: 18px;
  }
  .scores {
    grid-template-columns: minmax(0, 1fr);
  }
  .rsvp-options {
    grid-template-columns: minmax(0, 1fr);
  }
  .date-rows li {
    grid-template-columns: minmax(0, 1fr);
    gap: 6px;
  }
  .confirm-when-fields {
    grid-template-columns: minmax(0, 1fr);
  }
  .rsvp-actions button {
    width: 100%;
  }
  .rsvp-summary {
    width: 100%;
  }
  .rsvp-summary > div {
    flex: 1;
    padding: 10px 14px;
  }
}
</style>
