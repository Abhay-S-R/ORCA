"""Generate official Project ORCA proposal document for Bhashini AI application."""
from pathlib import Path
from fpdf import FPDF


class BhashiniProposalPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 15)
        self.set_text_color(15, 45, 90)
        self.cell(0, 8, "PROJECT ORCA - PRODUCT SPECIFICATION", new_x="LMARGIN", new_y="NEXT", align="C")
        self.set_font("Helvetica", "I", 9.5)
        self.set_text_color(90, 100, 115)
        self.cell(0, 5, "Product Architecture & Bhashini AI Services Integration Proposal", new_x="LMARGIN", new_y="NEXT", align="C")
        self.ln(3)
        self.set_draw_color(15, 45, 90)
        self.set_line_width(0.5)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(130, 130, 130)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}} - ORCA Marine Decision Support | Digital India Bhashini Application", align="C")

    def chapter_title(self, title):
        self.set_font("Helvetica", "B", 10.5)
        self.set_fill_color(235, 243, 255)
        self.set_text_color(15, 45, 90)
        self.cell(0, 6, f"  {title}", new_x="LMARGIN", new_y="NEXT", fill=True)
        self.ln(2)

    def body_text(self, text):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(35, 40, 50)
        self.multi_cell(0, 4.5, text)
        self.ln(2)


def generate_pdf():
    pdf = BhashiniProposalPDF()
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.chapter_title("1. Executive Summary & Product Overview")
    pdf.body_text(
        "Project ORCA (Oceanic Resource & Coastal Advisory) is an agentic AI-powered maritime decision support "
        "and marine safety advisory platform engineered for traditional artisanal fishermen, coastal communities, and "
        "maritime authorities across India. Operating across India's 9 coastal states (Tamil Nadu, Kerala, Andhra Pradesh, "
        "Karnataka, Maharashtra, Gujarat, Odisha, West Bengal, and Goa), ORCA synthesizes live oceanographic telemetry "
        "(wave heights, wind speeds, ocean currents, sea surface temperatures), potential fishing zones (PFZ), and geopolitical "
        "boundary proximity (International Maritime Boundary Lines / IMBL and Marine Protected Areas / MPAs) to deliver "
        "deterministic, life-saving GO / CAUTION / NO-GO navigation decisions."
    )

    pdf.chapter_title("2. Target Beneficiaries & The Need for Bhashini AI")
    pdf.body_text(
        "India's coastal waters sustain over 4 million traditional marine fishermen operating motorized non-mechanical and "
        "small mechanized boats. These communities face severe operational hazards:\n"
        "- Linguistic Diversity: Fisherfolk communicate primarily in coastal languages: Tamil, Malayalam, Telugu, Kannada, "
        "Marathi, Gujarati, Odia, and Bengali.\n"
        "- Digital & Literacy Barriers: Text-heavy mobile user interfaces are inaccessible to non-literate and semi-literate crew.\n"
        "- Harsh Physical Marine Environment: High engine vibration, wet hands, salt spray, tropical sun glare, and high "
        "noise levels from 2-stroke boat motors make handheld typing and reading practically impossible at sea.\n\n"
        "Bhashini AI represents the critical national infrastructure to solve this challenge: enabling a complete, hands-free "
        "voice-in / voice-out interaction loop that communicates mission-critical safety advice directly in the fisherman's mother tongue."
    )

    pdf.chapter_title("3. Detailed Usage of Bhashini AI Services")
    pdf.body_text(
        "ORCA integrates Bhashini AI across its Language & User Interaction Pipeline (Agent 1) as follows:\n\n"
        "1. Automatic Speech Recognition (ASR): Transcribes fishermen's spoken vernacular audio into text across 10 coastal languages.\n"
        "2. Denoiser & Voice Activity Detection (VAD): Vital for filtering out boat motor drone, sea spray, and wind noise before speech transcription.\n"
        "3. Text & Audio Language Detection (TLD & ALD): Automatically identifies spoken dialects without requiring manual language toggling.\n"
        "4. Neural Machine Translation (NMT): Translates vernacular queries to English for scientific oceanographic reasoning, and back-translates safety verdicts to the user's dialect.\n"
        "5. Text-to-Speech (TTS): Vocalizes authoritative safety verdicts (e.g., 'Rough sea conditions off Pamban tomorrow; 17nm from IMBL boundary; Stay in port') over device audio.\n"
        "6. Transliteration & Text Normalization (ITN): Resolves colloquial Latin-scripted vernacular queries (Tanglish/Hinglish) and accurately normalizes maritime numeric units (knots, nautical miles, meters)."
    )

    pdf.add_page()
    pdf.chapter_title("4. End-to-End Operational Workflow")
    pdf.body_text(
        "The complete user interaction workflow operates in 5 stages:\n"
        "Step 1 (Voice Ingress): The fisherman taps the microphone and asks naturally: 'Naalai kaalai Thoothukudi arugil meenpidikka povadhu paadhukaappaanadha?' (Is it safe to fish near Thoothukudi tomorrow morning?)\n"
        "Step 2 (Bhashini ASR & Denoiser): Boat engine noise is suppressed; speech is transcribed to Tamil script.\n"
        "Step 3 (Bhashini NMT): Query is translated to English: 'Is it safe to go out fishing tomorrow morning near Thoothukudi?'\n"
        "Step 4 (Multi-Agent Scientific Reasoning): ORCA backend evaluates Open-Meteo waves, GEBCO bathymetry, and Sri Lanka boundary proximity, computing a deterministic safety verdict.\n"
        "Step 5 (Bhashini Egress & Voice Advisory): Bhashini NMT translates the safety advisory into native Tamil, and Bhashini TTS speaks the warning aloud to the crew."
    )

    pdf.chapter_title("5. Technical Architecture & Deployment Scope")
    pdf.body_text(
        "- Frontend Client: Modern Progressive Web App (Next.js 15, Tailwind CSS, Web Audio API, service worker caching for offline resilience).\n"
        "- Backend Engine: High-performance Python FastAPI service with asynchronous LangGraph orchestration.\n"
        "- Reliability & Fallback: Bhashini REST endpoints serve as the primary cloud tier, with local cached rungs ensuring continuous zero-crash operation.\n"
        "- Target Request Volume: Pilot phase expects 5,000 to 25,000 speech recognition and translation API calls per month across coastal field hubs."
    )

    pdf.chapter_title("6. Public Good & Data Privacy Alignment")
    pdf.body_text(
        "- Public Good Focus: ORCA is a non-commercial disaster risk reduction and humanitarian marine safety project.\n"
        "- Privacy Safeguards: Audio streams and queries are processed solely for real-time safety evaluation. No personal identity data is commercialized or retained.\n"
        "- Digital India Alignment: Leverages open national datasets (INCOIS, IMD, NDMA CAP, Bhashini ULCA) to advance maritime safety and regional empowerment."
    )

    out_file = Path(r"c:\Users\Abhay S R\Desktop\orca\ORCA_Bhashini_Integration_Proposal.pdf")
    pdf.output(str(out_file))
    print(f"Generated successfully: {out_file} ({out_file.stat().st_size} bytes)")


if __name__ == "__main__":
    generate_pdf()
