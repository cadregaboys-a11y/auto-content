import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { finalize, switchMap, takeWhile, timer } from 'rxjs';

interface PipelineVideo {
  id: string;
  title: string;
  url: string;
  license: string;
  source_preview_url: string;
}

interface PipelineStage {
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  message: string;
}

interface ProcessingJob {
  id: string;
  keyword: string;
  videoId?: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  stage: string;
  progress: number;
  message: string;
  stages: PipelineStage[];
  video?: PipelineVideo;
  result?: {
    output_file: string;
    script: string;
    scene_summary: string;
    duration_seconds: number;
    preview_url: string;
    download_url: string;
  };
  error?: string;
}

@Component({
  selector: 'app-root',
  imports: [FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);

  protected keyword = 'urban gardening';
  protected brief = 'Un dettaglio sorprendente che vale la pena conoscere';
  protected rightsConfirmed = false;
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly pipelineJob = signal<ProcessingJob | null>(null);
  protected readonly stageLabels: Record<string, string> = {
    search: 'Ricerca YouTube e verifica licenze',
    download: 'Video scaricato',
    frame_analysis: 'Analisi visiva locale',
    source_transcription: 'Trascrizione video · Whisper',
    story_generation: 'Script narrativo',
    // elevenlabs_synthesis: 'Voce narrante · ElevenLabs',
    elevenlabs_synthesis: 'Sintesi voce · TTS locale',
    narration_transcription: 'Timestamp parole · Whisper',
    rendering: 'Montaggio 9:16 e sottotitoli',
  };

  protected download(): void {
    const keyword = this.keyword.trim();
    const brief = this.brief.trim();
    if (
      keyword.length < 2 ||
      brief.length < 5 ||
      !this.rightsConfirmed ||
      this.loading()
    ) {
      return;
    }

    this.loading.set(true);
    this.error.set('');
    this.pipelineJob.set(null);

    this.http
      .post<ProcessingJob>('/api/video-jobs', {
        keyword,
        brief,
        language: 'it',
        rightsConfirmed: this.rightsConfirmed,
      })
      .pipe(
        switchMap((initialJob) => {
          this.pipelineJob.set(initialJob);
          return timer(500, 1200).pipe(
            switchMap(() => this.http.get<ProcessingJob>(`/api/video-jobs/${initialJob.id}`)),
            takeWhile(
              (job) => job.status === 'queued' || job.status === 'running',
              true,
            ),
          );
        }),
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (job) => this.pipelineJob.set(job),
        error: (error: unknown) => {
          const message =
            error instanceof HttpErrorResponse &&
            typeof error.error?.error === 'string'
              ? error.error.error
              : 'Impossibile avviare il job. Controlla API, Python e servizi richiesti.';
          this.error.set(message);
        },
      });
  }
}
