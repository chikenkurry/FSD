CREATE TABLE public.confirmed_selections (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    plan_id uuid NOT NULL,
    recommendation_run_id uuid NOT NULL,
    version bigint DEFAULT 1 NOT NULL,
    selected_activity_id uuid,
    selected_start_time timestamp with time zone NOT NULL,
    selected_end_time timestamp with time zone NOT NULL,
    final_cost_per_person numeric(10,2) NOT NULL,
    selection_details jsonb DEFAULT '{}'::jsonb NOT NULL,
    confirmed_by_user_id uuid NOT NULL,
    confirmed_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.integration_rounds (
    id uuid NOT NULL,
    plan_id uuid NOT NULL,
    state text NOT NULL,
    option_revision bigint NOT NULL,
    option_snapshot_id uuid NOT NULL,
    definition jsonb NOT NULL,
    settings jsonb NOT NULL,
    publish_operation_id uuid NOT NULL,
    freeze_operation_id uuid NOT NULL,
    response_snapshot_id text,
    last_run_id text
);

CREATE TABLE public.invitations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    plan_id uuid NOT NULL,
    created_by uuid NOT NULL,
    token character varying(64) NOT NULL,
    status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone,
    max_uses bigint DEFAULT 0,
    use_count bigint DEFAULT 0
);

CREATE TABLE public.plan_members (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    plan_id uuid NOT NULL,
    user_id uuid NOT NULL,
    display_name character varying(100) NOT NULL,
    role character varying(50) DEFAULT 'MEMBER'::character varying NOT NULL,
    joined_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.plan_rounds (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    plan_id uuid NOT NULL,
    round_number bigint DEFAULT 1 NOT NULL,
    deadline_at timestamp with time zone,
    is_active boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.plans (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    category character varying(50) NOT NULL,
    state character varying(50) DEFAULT 'DRAFT'::character varying NOT NULL,
    created_by_user_id uuid NOT NULL,
    time_window_start timestamp with time zone,
    time_window_end timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.proposed_activities (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    plan_id uuid NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    est_cost_per_person numeric(10,2) DEFAULT 0 NOT NULL,
    duration_minutes bigint DEFAULT 60 NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.question_presets (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    category character varying(50) NOT NULL,
    title character varying(255) NOT NULL,
    type character varying(50) NOT NULL,
    description text,
    is_required boolean DEFAULT false,
    sort_order integer DEFAULT 0,
    options jsonb
);

CREATE TABLE public.questions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    plan_id uuid NOT NULL,
    title character varying(255) NOT NULL,
    type character varying(50) NOT NULL,
    description text,
    is_required boolean DEFAULT false NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    options jsonb,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);

CREATE TABLE public.reopen_operations (
    operation_id uuid NOT NULL,
    source_round_id uuid NOT NULL,
    new_round_id uuid NOT NULL
);

CREATE TABLE public.selections (
    round_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    run_id text NOT NULL,
    candidate_id text NOT NULL,
    confirmed_by uuid NOT NULL,
    confirmed_at timestamp with time zone NOT NULL
);

CREATE TABLE public.sessions (
    token_hash text NOT NULL,
    user_id uuid NOT NULL,
    expires_at timestamp with time zone NOT NULL
);

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    username character varying(255) NOT NULL
);

ALTER TABLE ONLY public.confirmed_selections
    ADD CONSTRAINT confirmed_selections_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.integration_rounds
    ADD CONSTRAINT integration_rounds_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.invitations
    ADD CONSTRAINT invitations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.plan_members
    ADD CONSTRAINT plan_members_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.plan_rounds
    ADD CONSTRAINT plan_rounds_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.plans
    ADD CONSTRAINT plans_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.proposed_activities
    ADD CONSTRAINT proposed_activities_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.question_presets
    ADD CONSTRAINT question_presets_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.questions
    ADD CONSTRAINT questions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.reopen_operations
    ADD CONSTRAINT reopen_operations_pkey PRIMARY KEY (operation_id);

ALTER TABLE ONLY public.selections
    ADD CONSTRAINT selections_pkey PRIMARY KEY (round_id);

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (token_hash);

ALTER TABLE ONLY public.confirmed_selections
    ADD CONSTRAINT uni_confirmed_selections_plan_id UNIQUE (plan_id);

ALTER TABLE ONLY public.selections
    ADD CONSTRAINT uni_selections_operation_id UNIQUE (operation_id);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

CREATE INDEX idx_integration_rounds_plan_id ON public.integration_rounds USING btree (plan_id);

CREATE INDEX idx_invitations_plan_id ON public.invitations USING btree (plan_id);

CREATE UNIQUE INDEX idx_invitations_token ON public.invitations USING btree (token);

CREATE INDEX idx_plan_members_user ON public.plan_members USING btree (user_id);

CREATE INDEX idx_plan_rounds_active ON public.plan_rounds USING btree (plan_id) WHERE (is_active = true);

CREATE INDEX idx_plans_created_by ON public.plans USING btree (created_by_user_id);

CREATE INDEX idx_plans_state ON public.plans USING btree (state);

CREATE INDEX idx_proposed_activities_plan ON public.proposed_activities USING btree (plan_id);

CREATE INDEX idx_questions_plan_id ON public.questions USING btree (plan_id);

CREATE INDEX idx_sessions_user_id ON public.sessions USING btree (user_id);

CREATE UNIQUE INDEX uq_plan_round ON public.plan_rounds USING btree (plan_id, round_number);

CREATE UNIQUE INDEX uq_plan_user ON public.plan_members USING btree (plan_id, user_id);

ALTER TABLE ONLY public.confirmed_selections
    ADD CONSTRAINT fk_confirmed_selections_selected_activity FOREIGN KEY (selected_activity_id) REFERENCES public.proposed_activities(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.invitations
    ADD CONSTRAINT fk_invitations_plan FOREIGN KEY (plan_id) REFERENCES public.plans(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.confirmed_selections
    ADD CONSTRAINT fk_plans_confirmed_selection FOREIGN KEY (plan_id) REFERENCES public.plans(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.plan_members
    ADD CONSTRAINT fk_plans_members FOREIGN KEY (plan_id) REFERENCES public.plans(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.proposed_activities
    ADD CONSTRAINT fk_plans_proposed_activities FOREIGN KEY (plan_id) REFERENCES public.plans(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.questions
    ADD CONSTRAINT fk_plans_questions FOREIGN KEY (plan_id) REFERENCES public.plans(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.plan_rounds
    ADD CONSTRAINT fk_plans_rounds FOREIGN KEY (plan_id) REFERENCES public.plans(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.plans
    ADD CONSTRAINT fk_users_created_plans FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);

ALTER TABLE ONLY public.plan_members
    ADD CONSTRAINT fk_users_memberships FOREIGN KEY (user_id) REFERENCES public.users(id);
