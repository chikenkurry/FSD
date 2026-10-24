# What to do?

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Professional organisations and companies, as well as friends and informal groups.
Organisers define a decision and invite members; members share their preferences,
review requirements, and respond to the confirmed choice.

## Product Purpose

Help groups compare real options and reach a decision that accounts for member
preferences and requirements. The interface must suit both formal and informal use.

## Capabilities and Constraints

The existing Vue app connects to Planning and Participation APIs. It supports guest
sessions, AI-assisted form creation (option overviews with Google Places for venues,
drafted questions and option fit, all editable before publishing), options with
sourced facts, invitations, a step-by-step member response flow, private response
review, submission, collection closure, recommendations, confirmation and RSVP.
Preserve these connected flows, server authority, privacy boundaries and mobile use.
The creator currently publishes options decisions; date and location fields provide
context rather than scheduled candidates. Company-level audience does not imply
enterprise SSO, tenant management or administrative capabilities already exist.

## Brand Commitments

Keep the product name. Avoid generic AI-generated styling. The visual language must
be credible for professional use and approachable for informal groups.

## Evidence on Hand

Working components in frontend/src and connected browser journeys in frontend/tests.
No customer testimonials, adoption metrics or enterprise deployment claims supplied.

## Product Principles

- Show the current decision state and the next available action clearly.
- Keep private answers and interpretation separate from shared results.
- Explain requirements and factual evidence without inventing certainty. Label AI
  estimates and third-party content with their origin.
- Ask the organiser for as little as possible; let AI suggest the rest.
- Make the same workflows usable on phones and desktop screens.
