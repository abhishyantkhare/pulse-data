"""add_aggregate_tables

Revision ID: 1772d3afeb49
Revises: 1103917126e8
Create Date: 2019-01-25 15:10:42.534258

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1772d3afeb49'
down_revision = '1103917126e8'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('dc_facility_aggregate',
    sa.Column('record_id', sa.Integer(), nullable=False),
    sa.Column('fips', sa.String(length=255), nullable=True),
    sa.Column('report_date', sa.DateTime(), nullable=True),
    sa.Column('report_granularity', sa.Enum('DAILY', 'WEEKLY', 'MONTHLY', name='report_granularity'), nullable=True),
    sa.Column('facility_name', sa.String(length=255), nullable=True),
    sa.Column('total_population', sa.Integer(), nullable=True),
    sa.Column('male_population', sa.Integer(), nullable=True),
    sa.Column('female_population', sa.Integer(), nullable=True),
    sa.Column('stsf_male_population', sa.Integer(), nullable=True),
    sa.Column('stsf_female_population', sa.Integer(), nullable=True),
    sa.Column('usms_gb_male_population', sa.Integer(), nullable=True),
    sa.Column('usms_gb_female_population', sa.Integer(), nullable=True),
    sa.Column('juvenile_male_population', sa.Integer(), nullable=True),
    sa.Column('juvenile_female_population', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('record_id'),
    sa.UniqueConstraint('fips', 'report_date', 'report_granularity')
    )
    op.create_table('fl_county_aggregate',
    sa.Column('record_id', sa.Integer(), nullable=False),
    sa.Column('fips', sa.String(length=255), nullable=True),
    sa.Column('report_date', sa.DateTime(), nullable=True),
    sa.Column('report_granularity', sa.Enum('DAILY', 'WEEKLY', 'MONTHLY', name='report_granularity'), nullable=True),
    sa.Column('county_name', sa.String(length=255), nullable=True),
    sa.Column('county_population', sa.Integer(), nullable=True),
    sa.Column('average_daily_population', sa.Integer(), nullable=True),
    sa.Column('date_reported', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('record_id'),
    sa.UniqueConstraint('fips', 'report_date', 'report_granularity')
    )
    op.create_table('fl_facility_aggregate',
    sa.Column('record_id', sa.Integer(), nullable=False),
    sa.Column('fips', sa.String(length=255), nullable=True),
    sa.Column('report_date', sa.DateTime(), nullable=True),
    sa.Column('report_granularity', sa.Enum('DAILY', 'WEEKLY', 'MONTHLY', name='report_granularity'), nullable=True),
    sa.Column('facility_name', sa.String(length=255), nullable=True),
    sa.Column('average_daily_population', sa.Integer(), nullable=True),
    sa.Column('number_felony_pretrial', sa.Integer(), nullable=True),
    sa.Column('number_misdemeanor_pretrial', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('record_id'),
    sa.UniqueConstraint('fips', 'report_date', 'report_granularity')
    )
    op.create_table('ga_county_aggregate',
    sa.Column('record_id', sa.Integer(), nullable=False),
    sa.Column('fips', sa.String(length=255), nullable=True),
    sa.Column('report_date', sa.DateTime(), nullable=True),
    sa.Column('report_granularity', sa.Enum('DAILY', 'WEEKLY', 'MONTHLY', name='report_granularity'), nullable=True),
    sa.Column('county_name', sa.String(length=255), nullable=True),
    sa.Column('total_number_of_inmates_in_jail', sa.Integer(), nullable=True),
    sa.Column('jail_capacity', sa.Integer(), nullable=True),
    sa.Column('number_of_inmates_sentenced_to_state', sa.Integer(), nullable=True),
    sa.Column('number_of_inmates_awaiting_trial', sa.Integer(), nullable=True),
    sa.Column('number_of_inmates_serving_county_sentence', sa.Integer(), nullable=True),
    sa.Column('number_of_other_inmates', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('record_id'),
    sa.UniqueConstraint('fips', 'report_date', 'report_granularity')
    )
    op.create_table('hi_facility_aggregate',
    sa.Column('record_id', sa.Integer(), nullable=False),
    sa.Column('fips', sa.String(length=255), nullable=True),
    sa.Column('report_date', sa.DateTime(), nullable=True),
    sa.Column('report_granularity', sa.Enum('DAILY', 'WEEKLY', 'MONTHLY', name='report_granularity'), nullable=True),
    sa.Column('facility_name', sa.String(length=255), nullable=True),
    sa.Column('design_bed_capacity', sa.Integer(), nullable=True),
    sa.Column('operation_bed_capacity', sa.Integer(), nullable=True),
    sa.Column('total_population', sa.Integer(), nullable=True),
    sa.Column('male_population', sa.Integer(), nullable=True),
    sa.Column('female_population', sa.Integer(), nullable=True),
    sa.Column('sentenced_felony_male_population', sa.Integer(), nullable=True),
    sa.Column('sentenced_felony_female_population', sa.Integer(), nullable=True),
    sa.Column('sentenced_felony_probation_male_population', sa.Integer(), nullable=True),
    sa.Column('sentenced_felony_probation_female_population', sa.Integer(), nullable=True),
    sa.Column('sentenced_misdemeanor_male_population', sa.Integer(), nullable=True),
    sa.Column('sentenced_misdemeanor_female_population', sa.Integer(), nullable=True),
    sa.Column('sentenced_pretrial_felony_male_population', sa.Integer(), nullable=True),
    sa.Column('sentenced_pretrial_felony_female_population', sa.Integer(), nullable=True),
    sa.Column('sentenced_pretrial_misdemeanor_male_population', sa.Integer(), nullable=True),
    sa.Column('sentenced_pretrial_misdemeanor_female_population', sa.Integer(), nullable=True),
    sa.Column('held_for_other_jurisdiction_male_population', sa.Integer(), nullable=True),
    sa.Column('held_for_other_jurisdiction_female_population', sa.Integer(), nullable=True),
    sa.Column('parole_violation_male_population', sa.Integer(), nullable=True),
    sa.Column('parole_violation_female_population', sa.Integer(), nullable=True),
    sa.Column('probation_violation_male_population', sa.Integer(), nullable=True),
    sa.Column('probation_violation_female_population', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('record_id'),
    sa.UniqueConstraint('fips', 'report_date', 'report_granularity')
    )
    op.create_table('ky_county_aggregate',
    sa.Column('record_id', sa.Integer(), nullable=False),
    sa.Column('fips', sa.String(length=255), nullable=True),
    sa.Column('report_date', sa.DateTime(), nullable=True),
    sa.Column('report_granularity', sa.Enum('DAILY', 'WEEKLY', 'MONTHLY', name='report_granularity'), nullable=True),
    sa.Column('county_name', sa.String(length=255), nullable=True),
    sa.Column('total_jail_beds', sa.Integer(), nullable=True),
    sa.Column('reported_population', sa.Integer(), nullable=True),
    sa.Column('male_population', sa.Integer(), nullable=True),
    sa.Column('female_population', sa.Integer(), nullable=True),
    sa.Column('class_d_male_population', sa.Integer(), nullable=True),
    sa.Column('class_d_female_population', sa.Integer(), nullable=True),
    sa.Column('community_custody_male_population', sa.Integer(), nullable=True),
    sa.Column('community_custody_female_population', sa.Integer(), nullable=True),
    sa.Column('alternative_sentence_male_population', sa.Integer(), nullable=True),
    sa.Column('alternative_sentence_female_population', sa.Integer(), nullable=True),
    sa.Column('controlled_intake_male_population', sa.Integer(), nullable=True),
    sa.Column('controlled_intake_female_population', sa.Integer(), nullable=True),
    sa.Column('parole_violators_male_population', sa.Integer(), nullable=True),
    sa.Column('parole_violators_female_population', sa.Integer(), nullable=True),
    sa.Column('federal_male_population', sa.Integer(), nullable=True),
    sa.Column('federal_female_population', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('record_id'),
    sa.UniqueConstraint('fips', 'report_date', 'report_granularity')
    )
    op.create_table('ny_facility_aggregate',
    sa.Column('record_id', sa.Integer(), nullable=False),
    sa.Column('fips', sa.String(length=255), nullable=True),
    sa.Column('report_date', sa.DateTime(), nullable=True),
    sa.Column('report_granularity', sa.Enum('DAILY', 'WEEKLY', 'MONTHLY', name='report_granularity'), nullable=True),
    sa.Column('facility_name', sa.String(length=255), nullable=True),
    sa.Column('census', sa.Integer(), nullable=True),
    sa.Column('in_house', sa.Integer(), nullable=True),
    sa.Column('boarded_in', sa.Integer(), nullable=True),
    sa.Column('boarded_out', sa.Integer(), nullable=True),
    sa.Column('sentenced', sa.Integer(), nullable=True),
    sa.Column('civil', sa.Integer(), nullable=True),
    sa.Column('federal', sa.Integer(), nullable=True),
    sa.Column('technical_parole_violators', sa.Integer(), nullable=True),
    sa.Column('state_readies', sa.Integer(), nullable=True),
    sa.Column('other_unsentenced', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('record_id'),
    sa.UniqueConstraint('fips', 'report_date', 'report_granularity')
    )
    op.create_table('tx_county_aggregate',
    sa.Column('record_id', sa.Integer(), nullable=False),
    sa.Column('fips', sa.String(length=255), nullable=True),
    sa.Column('report_date', sa.DateTime(), nullable=True),
    sa.Column('report_granularity', sa.Enum('DAILY', 'WEEKLY', 'MONTHLY', name='report_granularity'), nullable=True),
    sa.Column('county_name', sa.String(length=255), nullable=True),
    sa.Column('pretrial_felons', sa.Integer(), nullable=True),
    sa.Column('convicted_felons', sa.Integer(), nullable=True),
    sa.Column('convicted_felons_sentenced_to_county_jail', sa.Integer(), nullable=True),
    sa.Column('parole_violators', sa.Integer(), nullable=True),
    sa.Column('parole_violators_with_new_charge', sa.Integer(), nullable=True),
    sa.Column('pretrial_misdemeanor', sa.Integer(), nullable=True),
    sa.Column('convicted_misdemeanor', sa.Integer(), nullable=True),
    sa.Column('bench_warrants', sa.Integer(), nullable=True),
    sa.Column('federal', sa.Integer(), nullable=True),
    sa.Column('pretrial_sjf', sa.Integer(), nullable=True),
    sa.Column('convicted_sjf_sentenced_to_county_jail', sa.Integer(), nullable=True),
    sa.Column('convicted_sjf_sentenced_to_state_jail', sa.Integer(), nullable=True),
    sa.Column('total_contract', sa.Integer(), nullable=True),
    sa.Column('total_population', sa.Integer(), nullable=True),
    sa.Column('total_other', sa.Integer(), nullable=True),
    sa.Column('total_capacity', sa.Integer(), nullable=True),
    sa.Column('available_beds', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('record_id'),
    sa.UniqueConstraint('fips', 'report_date', 'report_granularity')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('tx_county_aggregate')
    op.drop_table('ny_facility_aggregate')
    op.drop_table('ky_county_aggregate')
    op.drop_table('hi_facility_aggregate')
    op.drop_table('ga_county_aggregate')
    op.drop_table('fl_facility_aggregate')
    op.drop_table('fl_county_aggregate')
    op.drop_table('dc_facility_aggregate')
    # ### end Alembic commands ###