# Various tests of the BiGG database

from sqlalchemy.engine import create_engine
from sqlalchemy.orm.session import Session
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, aliased
from sqlalchemy import create_engine, desc, func, or_
import pytest
import sys
from cobra.io import read_sbml_model
import pytest
import numpy
from os.path import abspath, dirname, join
from numpy.testing import assert_almost_equal
from decimal import Decimal

from ome.models import *
from ome.base import Session
from ome import settings
from ome.dumping.model_dumping import dump_model
from ome.loading.model_loading.parse import convert_ids


def sharedReactions(model1, model2):
    session = Session()
    modelquery1 = session.query(Model).filter(Model.bigg_id == model1).first()
    modelquery2 = session.query(Model).filter(Model.bigg_id == model2).first()
    query = (session
             .query(ModelReaction.reaction_id)
             .distinct()
             .filter(or_(ModelReaction.model_id == modelquery1.id,
                         ModelReaction.model_id == modelquery2.id)))
    for r in query.all():
        session.query(Reaction).filter(Reaction.id == r).one().name
    print '' + str(query.count()) + ' shared reactions'
    #print ' this query was used: ' + str(query)
    session.close()

    
def shardMetabolites(model1, model2):
    session = Session()
    modelquery1 = session.query(Model).filter(Model.bigg_id == model1).first()
    modelquery2 = session.query(Model).filter(Model.bigg_id == model2).first()
    query = session.query(CompartmentalizedComponent.component_id).distinct().join(ModelCompartmentalizedComponent).filter(or_(ModelCompartmentalizedComponent.model_id == modelquery1.id, ModelCompartmentalizedComponent.model_id == modelquery2.id))
    for m in query.all():
        session.query(Metabolite).filter(Metabolite.id == m).one().name
    print '' + str(query.count()) + ' shared metabolites' 
    #print ' this query was used: ' + str(query)
    session.close()


def getModelsForReaction(reaction):
    session = Session()
    query = session.query(ModelReaction).distinct(ModelReaction.model_id).filter(ModelReaction.reaction_id == reaction.id)
    print query.count
    for rm in query.all():
        model = session.query(Model).filter(Model.id == rm.model_id).one()
        print model.bigg_id
    session.close()
    

def getModelsForMetabolite(metaboliteName):
    session = Session()
    metabolite = session.query(Metabolite).filter(Metabolite.name == metaboliteName)
    for cc in session.query(CompartmentalizedComponent).filter(CompartmentalizedComponent.component_id == metabolite.id).all():
        for mcc in session.query(ModelCompartmentalizedComponent).filter(ModelCompartmentalizedComponent.compartmentalized_component_id == cc.id).all():
            model = session.query(Model).filter(Model.id == mcc.model_id).first()
            print model.bigg_id
    session.close()
    

# TODO finish
def getMetabolitesOfReaction(reactionName):
    session = Session()
    reaction = session.query(Reaction).filter(Reaction.name == reactionName)
    for met in session.query(ReactionMatrix).filter(ReactionMatrix.reaction_id == reaction.id).all():
        cc = session.query(CompartmentalizedComponent).filter(CompartmentalizedComponent.id == met.compartmentalized_component_id).first()
        print session.query(Metabolite).filter(Metabolite.id == cc.component_id).name
    session.close()

@pytest.fixture(scope='function')
def session(request):
    """Make a session"""
    def teardown():
        Session.close_all()
    request.addfinalizer(teardown)

    return Session()


def test_compartment_names(session):
    assert (session
            .query(Compartment.name)
            .filter(Compartment.bigg_id == 'c')
            .first())[0] == 'cytosol'


def test_sbml_input_output(session):
    try_one = True

    published_models = {}
    with open(settings.model_genome_file, 'r') as f:
        for line in f.readlines():
            model_file = join(settings.data_directory, 'models', line.split(',')[0])
            try:
                print('Loading %s' % model_file)
                model = read_sbml_model(model_file)
            except IOError:
                print('Could not find model file %s' % model_file)
                continue
            published_models[model.id] = model
            if try_one:
                break
                
    if try_one:
        model_db = (session
                    .query(Model)
                    .filter(Model.bigg_id==published_models.keys()[0])
                    .all())
    else:
        model_db = (session
                    .query(Model)
                    .all())
    for model in model_db:
        try:
            published_model = published_models[model.bigg_id]
        except KeyError:
            print('Could not find published model for database model %s' % model.bigg_id)
            continue

        print('Testing %s' % model.bigg_id)

        database_model = dump_model(model.bigg_id)

        assert len(database_model.reactions) == len(published_model.reactions)
        assert len(database_model.metabolites) == len(published_model.metabolites)
        assert len(database_model.genes) == len(published_model.genes)

        # check reaction coefficients for GLCtex
        published_model_converted, _ = convert_ids(published_model.copy(), 'cobrapy')
        if 'GLCtex' in published_model_converted.reactions and 'GLCtex_copy1' in database_model.reactions:
            print 'Testing GLCtex'
            r1 = published_model_converted.reactions.get_by_id('GLCtex')
            r2 = database_model.reactions.get_by_id('GLCtex_copy1')
            for met in r1.metabolites:
                assert (r1.metabolites[published_model_converted.metabolites.get_by_id(met.id)] ==
                        r2.metabolites[database_model.metabolites.get_by_id(met.id)])
                
        solution1 = database_model.optimize()
        solution2 = published_model.optimize()
        # for k, v in sorted(solution1.x_dict.items(), key=lambda x: abs(x[1])):
        #     if k in solution2.x_dict:
        #         print k, solution1.x_dict[k], solution2.x_dict[k]
        #         r1 = database_model.reactions.get_by_id(k)
        #         r2 = published_model.reactions.get_by_id(k)
        #         if r1.lower_bound != r2.lower_bound or r1.upper_bound != r2.upper_bound:
        #             print '(%.2f, %.2f) (%.2f, %.2f)' % (r1.lower_bound, r1.upper_bound,
        #                                                  r2.lower_bound, r2.upper_bound)
        #         print
        #     elif k.split('_copy')[0] in solution2.x_dict:
        #         print k, solution1.x_dict[k], solution2.x_dict[k.split('_copy')[0]]
        #         r1 = database_model.reactions.get_by_id(k)
        #         r2 = published_model.reactions.get_by_id(k.split('_copy')[0])
        #         if r1.lower_bound != r2.lower_bound or r1.upper_bound != r2.upper_bound:
        #             print '(%.2f, %.2f) (%.2f, %.2f)' % (r1.lower_bound, r1.upper_bound,
        #                                                  r2.lower_bound, r2.upper_bound)
        #         print
        #     else:
        #         print k, solution1.x_dict[k]
        #         print '%s not in published model' % k

        # for r in database_model.reactions:
        #     if '_copy' in r:
        #         r_p = published_model.reactions.get_by_id(r.notes['original_bigg_id'])
        #         print r.id, (solution1.x_dict[r.id] if r.id in solution1.x_dict else '-'), r_p.id, (solution2.x_dict[r_p.id] if r_p.id in solution2.x_dict else '-')
        #         print '(%.2f, %.2f) (%.2f, %.2f)' % (r.lower_bound, r.upper_bound,
        #                                              r_p.lower_bound, r_p.upper_bound)
        #         print

        assert_almost_equal(solution1.f, solution2.f, decimal=5)

def test_dad_2(session):
    """Tests for a bug that occurs with dad__2_c vs. dad_2_c. Fails if you load
    iAF1260 then iMM904.

    In [44]: session.query(Component.bigg_id, Compartment.bigg_id, Model.bigg_id, Reaction.bigg_id).join(CompartmentalizedComponent, CompartmentalizedComponent.component_id==Component.id).join(Compartment, Compartment.id==CompartmentalizedComponent.compartment_id).join(ReactionMatrix, ReactionMatrix.compartmentalized_component_id==CompartmentalizedComponent.id).join(Reaction).join(ModelReaction).join(Model).filter(Model.bigg_id=='iAF1260').filter(Reaction.bigg_id.like('DADA')).all()

    Out[44]:
    [(u'dad__2', u'c', u'iAF1260', u'DADA'),
    (u'din', u'c', u'iAF1260', u'DADA'),
    (u'h2o', u'c', u'iAF1260', u'DADA'),
    (u'h', u'c', u'iAF1260', u'DADA'),
    (u'nh4', u'c', u'iAF1260', u'DADA'),
    (u'dad_2', u'c', u'iAF1260', u'DADA')]

    """
    res_db = (session
              .query(Component.bigg_id, Compartment.bigg_id, Model.bigg_id, Reaction.bigg_id)
              .join(CompartmentalizedComponent, CompartmentalizedComponent.component_id==Component.id)
              .join(Compartment, Compartment.id==CompartmentalizedComponent.compartment_id)
              .join(ReactionMatrix, ReactionMatrix.compartmentalized_component_id==CompartmentalizedComponent.id)
              .join(Reaction)
              .join(ModelReaction)
              .join(Model)
              .filter(Model.bigg_id=='iAF1260')
              .filter(Reaction.bigg_id == 'DADA')
              .filter(Component.bigg_id.like('dad_%2'))
              .all())
    session.close()
    assert len(res_db) == 1


def test_reaction_matrix(session):
    matrix = (session
              .query(Reaction.bigg_id, ReactionMatrix.stoichiometry, Metabolite)
              .join(ReactionMatrix, ReactionMatrix.reaction_id == Reaction.id)
              .filter(Reaction.bigg_id == 'GLCtex')
              .join(CompartmentalizedComponent)
              .join(Metabolite)
              .all())
    assert Decimal(1.0) in [x[1] for x in matrix]
    assert Decimal(-1.0) in [x[1] for x in matrix]


def test_models_for_bigg_style_ids(session):
    """Make sure all models use BiGG style IDs by checking for 'pyr'."""
    has_pyr = {}
    for model in session.query(Model).all():
        mcc = (session
               .query(ModelCompartmentalizedComponent)
               .join(Model,
                     Model.id == ModelCompartmentalizedComponent.model_id)
               .join(CompartmentalizedComponent,
                     CompartmentalizedComponent.id == ModelCompartmentalizedComponent.compartmentalized_component_id)
               .join(Component,
                     Component.id == CompartmentalizedComponent.component_id)
               .filter(Model.id == model.id)
               .filter(Component.bigg_id =="pyr")
               .first())
        has_pyr[model.bigg_id] = (mcc is not None)
    print 'No pyr: %s' % ', '.join([k for k, v in has_pyr.iteritems() if not v])
    assert all(has_pyr.values())


if __name__ == "__main__":
    if len(sys.argv) == 4:
        if str(sys.argv[1]) == 'models':
            model1 = str(sys.argv[2])
            model2 = str(sys.argv[3])
            #print "the reations that are shared between these two models are:"
            sharedReactions(model1, model2)
            #print "the metabolites that are shared between these two models are:"
            shardMetabolites(model1, model2)
