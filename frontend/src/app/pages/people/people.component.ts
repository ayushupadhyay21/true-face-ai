import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { toApiError } from '../../core/api-error';
import { Person } from '../../core/api.types';
import { errorCodeText } from '../../core/messages';
import { IconComponent } from '../../shared/icon.component';

interface Card {
  id: string;
  snapshotUrl: string;
  createdAt: string;
  embeddingCount: number;
  name: string;
  externalId: string;
  saving: boolean;
  deleting: boolean;
  error: string | null;
}

interface KnownRow {
  id: string;
  name: string;
  externalId: string | null;
  status: string;
  embeddingCount: number;
  createdAt: string;
  snapshotUrl: string;
  deleting: boolean;
}

interface Preview {
  url: string;
  name: string;
}

type SortOrder = 'recent' | 'oldest';

/**
 * People directory: known (named, ACTIVE/PENDING/DISABLED) people, plus a Google-Photos-style
 * review queue of faces Live View auto-bucketed (state UNASSIGNED) but has no name yet. Naming
 * one flips it to ACTIVE, so it is recognized from then on and moves into the known list.
 */
@Component({
  selector: 'app-people',
  imports: [FormsModule, IconComponent, RouterLink, DatePipe],
  templateUrl: './people.component.html',
})
export class PeopleComponent implements OnInit {
  private readonly api = inject(ApiService);

  protected readonly cards = signal<Card[]>([]);
  protected readonly known = signal<KnownRow[]>([]);
  protected readonly loading = signal(false);
  protected readonly loadError = signal<string | null>(null);
  protected readonly preview = signal<Preview | null>(null);
  protected readonly sortOrder = signal<SortOrder>('recent');
  protected readonly search = signal('');

  protected readonly sortedCards = computed(() => {
    const list = [...this.cards()];
    list.sort((a, b) => (this.sortOrder() === 'recent' ? (a.createdAt < b.createdAt ? 1 : -1) : (a.createdAt > b.createdAt ? 1 : -1)));
    return list;
  });

  protected readonly filteredKnown = computed(() => {
    const term = this.search().trim().toLowerCase();
    if (!term) return this.known();
    return this.known().filter(
      (k) => k.name.toLowerCase().includes(term) || (k.externalId ?? '').toLowerCase().includes(term),
    );
  });

  protected readonly totalPeople = computed(() => this.known().length + this.cards().length);
  protected readonly activeCount = computed(() => this.known().filter((k) => k.status === 'ACTIVE').length);
  protected readonly totalEmbeddings = computed(
    () =>
      this.known().reduce((sum, k) => sum + k.embeddingCount, 0) +
      this.cards().reduce((sum, c) => sum + c.embeddingCount, 0),
  );

  ngOnInit(): void {
    void this.refresh();
  }

  protected async refresh(): Promise<void> {
    this.loading.set(true);
    this.loadError.set(null);
    try {
      const people = await this.api.listPeople();
      const unassigned = people.filter((p) => p.status === 'UNASSIGNED');
      unassigned.sort((a, b) => (a.created_at < b.created_at ? 1 : -1)); // newest first
      this.cards.set(
        unassigned.map((p) => ({
          id: p.id,
          snapshotUrl: this.api.snapshotUrl(p.id),
          createdAt: p.created_at,
          embeddingCount: p.embedding_count,
          name: '',
          externalId: '',
          saving: false,
          deleting: false,
          error: null,
        })),
      );

      const rest = people.filter((p) => p.status !== 'UNASSIGNED');
      rest.sort((a: Person, b: Person) => a.name.localeCompare(b.name));
      this.known.set(
        rest.map((p) => ({
          id: p.id,
          name: p.name,
          externalId: p.external_id,
          status: p.status,
          embeddingCount: p.embedding_count,
          createdAt: p.created_at,
          snapshotUrl: this.api.snapshotUrl(p.id),
          deleting: false,
        })),
      );
    } catch (err) {
      this.loadError.set(errorCodeText(toApiError(err).code, toApiError(err).message));
    } finally {
      this.loading.set(false);
    }
  }

  protected setSortOrder(value: string): void {
    this.sortOrder.set(value as SortOrder);
  }

  protected setSearch(value: string): void {
    this.search.set(value);
  }

  protected setName(id: string, name: string): void {
    this.patch(id, { name, error: null });
  }

  protected setExternalId(id: string, externalId: string): void {
    this.patch(id, { externalId, error: null });
  }

  protected async save(card: Card): Promise<void> {
    const name = card.name.trim();
    if (!name) {
      this.patch(card.id, { error: 'Enter a name' });
      return;
    }
    this.patch(card.id, { saving: true, error: null });
    try {
      const person = await this.api.assignPerson(card.id, {
        name,
        ...(card.externalId.trim() ? { external_id: card.externalId.trim() } : {}),
      });
      this.cards.update((list) => list.filter((c) => c.id !== card.id));
      this.known.update((list) =>
        [
          ...list,
          {
            id: person.id,
            name: person.name,
            externalId: person.external_id,
            status: person.status,
            embeddingCount: person.embedding_count,
            createdAt: person.created_at,
            snapshotUrl: this.api.snapshotUrl(person.id),
            deleting: false,
          },
        ].sort((a, b) => a.name.localeCompare(b.name)),
      );
    } catch (err) {
      const e = toApiError(err);
      this.patch(card.id, { saving: false, error: errorCodeText(e.code, e.message) });
    }
  }

  /** Deletes an unnamed face (and its stored embedding). Irreversible: confirm first. */
  protected async deleteCard(card: Card): Promise<void> {
    if (!confirm('Delete this unnamed face? This cannot be undone.')) return;
    this.patch(card.id, { deleting: true, error: null });
    try {
      await this.api.deletePerson(card.id);
      this.cards.update((list) => list.filter((c) => c.id !== card.id));
    } catch (err) {
      const e = toApiError(err);
      this.patch(card.id, { deleting: false, error: errorCodeText(e.code, e.message) });
    }
  }

  /** Deletes a known person and all their stored embeddings. Irreversible: confirm first. */
  protected async deleteKnown(row: KnownRow): Promise<void> {
    if (!confirm(`Delete "${row.name}" and all their stored face data? This cannot be undone.`)) return;
    this.known.update((list) => list.map((k) => (k.id === row.id ? { ...k, deleting: true } : k)));
    try {
      await this.api.deletePerson(row.id);
      this.known.update((list) => list.filter((k) => k.id !== row.id));
    } catch (err) {
      const e = toApiError(err);
      this.loadError.set(errorCodeText(e.code, e.message));
      this.known.update((list) => list.map((k) => (k.id === row.id ? { ...k, deleting: false } : k)));
    }
  }

  /** Hides a snapshot <img> that 404s (no snapshot stored for this person). */
  protected hideOnError(event: Event): void {
    (event.target as HTMLImageElement).style.display = 'none';
  }

  /** Opens the full-size snapshot in a lightbox overlay. */
  protected showPreview(url: string, name: string): void {
    this.preview.set({ url, name });
  }

  protected closePreview(): void {
    this.preview.set(null);
  }

  private patch(id: string, changes: Partial<Card>): void {
    this.cards.update((list) => list.map((c) => (c.id === id ? { ...c, ...changes } : c)));
  }
}
